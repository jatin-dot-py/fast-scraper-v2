package main

import (
	"crypto/tls"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"
)

// Result represents a single URL scraping result
type Result struct {
	URL           string  `json:"url"`
	StatusCode    int     `json:"status_code,omitempty"`
	Content       string  `json:"content,omitempty"`
	Error         string  `json:"error,omitempty"`
	ElapsedTime   float64 `json:"elapsed_seconds"`
	Success       bool    `json:"success"`
	ProxyUsed     string  `json:"proxy_used"`
}

// Response represents the overall response from the scraper
type Response struct {
	Results        []Result `json:"results"`
	Total          int      `json:"total"`
	Successful     int      `json:"successful"`
	Failed         int      `json:"failed"`
	TotalTimeSeconds float64 `json:"total_time_seconds"`
	ProxyTypeUsed  string   `json:"proxy_type_used"`
}

var userAgents = []string{
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
}

func main() {
	// Parse command line arguments
	urlsFlag := flag.String("urls", "", "Comma-separated list of URLs to scrape")
	proxiesFlag := flag.String("proxies", "", "Comma-separated list of proxies to use")
	proxyTypeFlag := flag.String("proxy-type", "datacenter", "Type of proxy (datacenter, residential, etc.)")
	timeoutFlag := flag.Int("timeout", 10, "Timeout in seconds for each request")
	maxRetriesFlag := flag.Int("max-retries", 3, "Maximum number of retries for each URL")
	
	flag.Parse()

	// Split URLs
	urls := strings.Split(*urlsFlag, ",")
	if len(urls) == 0 || (len(urls) == 1 && urls[0] == "") {
		fmt.Fprintf(os.Stderr, "Error: No URLs provided\n")
		os.Exit(1)
	}

	// Clean up URLs
	var cleanUrls []string
	for _, u := range urls {
		u = strings.TrimSpace(u)
		if u != "" {
			cleanUrls = append(cleanUrls, u)
		}
	}

	// Split proxies
	var proxies []string
	if *proxiesFlag != "" {
		for _, p := range strings.Split(*proxiesFlag, ",") {
			p = strings.TrimSpace(p)
			if p != "" {
				proxies = append(proxies, p)
			}
		}
	}

	// Performance optimization: Seed the random number generator
	rand.Seed(time.Now().UnixNano())

	// Scrape URLs concurrently
	startTime := time.Now()
	results := scrapeURLs(cleanUrls, proxies, *proxyTypeFlag, *timeoutFlag, *maxRetriesFlag)
	elapsedTime := time.Since(startTime).Seconds()

	// Count successful and failed results
	successful := 0
	for _, result := range results {
		if result.Success {
			successful++
		}
	}
	failed := len(results) - successful

	// Prepare response
	response := Response{
		Results:          results,
		Total:            len(results),
		Successful:       successful,
		Failed:           failed,
		TotalTimeSeconds: elapsedTime,
		ProxyTypeUsed:    *proxyTypeFlag,
	}

	// Write response as JSON to stdout
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(response); err != nil {
		fmt.Fprintf(os.Stderr, "Error encoding response to JSON: %v\n", err)
		os.Exit(1)
	}
}

func scrapeURLs(urls []string, proxies []string, proxyType string, timeout int, maxRetries int) []Result {
	// Create a wait group to track goroutines
	var wg sync.WaitGroup
	
	// Create a channel to collect results
	resultsChan := make(chan Result, len(urls))
	
	// Process each URL concurrently
	for _, url := range urls {
		wg.Add(1)
		go func(url string) {
			defer wg.Done()
			
			// Scrape the URL with retries
			result := scrapeURL(url, proxies, proxyType, timeout, maxRetries)
			resultsChan <- result
		}(url)
	}
	
	// Wait for all goroutines to complete
	wg.Wait()
	close(resultsChan)
	
	// Collect results from channel
	var results []Result
	for result := range resultsChan {
		results = append(results, result)
	}
	
	return results
}

func scrapeURL(targetURL string, proxies []string, proxyType string, timeout int, maxRetries int) Result {
	startTime := time.Now()
	
	for attempt := 0; attempt < maxRetries; attempt++ {
		// Create a custom HTTP client
		client := &http.Client{
			Timeout: time.Duration(timeout) * time.Second,
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{
					InsecureSkipVerify: true, // Disable SSL verification for performance
				},
				MaxIdleConns:          100,
				MaxIdleConnsPerHost:   10,
				MaxConnsPerHost:       10,
				IdleConnTimeout:       30 * time.Second,
				TLSHandshakeTimeout:   10 * time.Second,
				ExpectContinueTimeout: 1 * time.Second,
				DisableKeepAlives:     false,
			},
		}
		
		// Apply proxy if available
		var proxyUsed string
		if len(proxies) > 0 {
			// Select a random proxy
			proxy := proxies[rand.Intn(len(proxies))]
			proxyUsed = proxy
			
			// Set up proxy URL
			proxyURL, err := url.Parse(proxy)
			if err == nil {
				client.Transport.(*http.Transport).Proxy = http.ProxyURL(proxyURL)
			} else {
				// If parsing fails, continue with next attempt
				continue
			}
		}
		
		// Create request
		req, err := http.NewRequest("GET", targetURL, nil)
		if err != nil {
			continue
		}
		
		// Set random user agent
		req.Header.Set("User-Agent", userAgents[rand.Intn(len(userAgents))])
		
		// Perform request
		resp, err := client.Do(req)
		
		// Handle errors
		if err != nil {
			// Try again if not the last attempt
			if attempt < maxRetries-1 {
				continue
			}
			
			// Return error on last attempt
			return Result{
				URL:         targetURL,
				Error:       fmt.Sprintf("All retry attempts failed: %v", err),
				ElapsedTime: time.Since(startTime).Seconds(),
				Success:     false,
				ProxyUsed:   proxyType,
			}
		}
		
		// Read response body
		defer resp.Body.Close()
		bodyBytes, err := io.ReadAll(resp.Body)
		if err != nil {
			// Try again if not the last attempt
			if attempt < maxRetries-1 {
				continue
			}
			
			// Return error on last attempt
			return Result{
				URL:         targetURL,
				StatusCode:  resp.StatusCode,
				Error:       fmt.Sprintf("Failed to read response body: %v", err),
				ElapsedTime: time.Since(startTime).Seconds(),
				Success:     false,
				ProxyUsed:   proxyType,
			}
		}
		
		// Success case
		return Result{
			URL:         targetURL,
			StatusCode:  resp.StatusCode,
			Content:     string(bodyBytes),
			ElapsedTime: time.Since(startTime).Seconds(),
			Success:     resp.StatusCode >= 200 && resp.StatusCode < 300,
			ProxyUsed:   proxyType,
		}
	}
	
	// This should never happen, but added for completeness
	return Result{
		URL:         targetURL,
		Error:       "Unknown failure in retry logic",
		ElapsedTime: time.Since(startTime).Seconds(),
		Success:     false,
		ProxyUsed:   proxyType,
	}
}