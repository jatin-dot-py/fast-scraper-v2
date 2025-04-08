import json
import logging
import os
import subprocess
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def scrape_with_go(urls: List[str], proxies: List[str] = None, proxy_type: str = "datacenter", 
                   timeout: int = 10, max_retries: int = 3) -> Dict[str, Any]:
    """
    Uses the Go scraper executable to scrape URLs concurrently.
    
    Args:
        urls: List of URLs to scrape
        proxies: List of proxy URLs to use
        proxy_type: Type of proxies
        timeout: Timeout in seconds for each request
        max_retries: Maximum number of retries for each URL
        
    Returns:
        Dictionary with scraping results
    """
    if not urls:
        return {
            "results": [],
            "total": 0,
            "successful": 0,
            "failed": 0,
            "total_time_seconds": 0,
            "proxy_type_used": proxy_type
        }
    
    # Path to the Go scraper executable
    go_scraper_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "go-scraper", "go-scraper")
    
    # Make sure the executable exists and is executable
    if not os.path.isfile(go_scraper_path):
        logger.error(f"Go scraper executable not found at {go_scraper_path}")
        raise FileNotFoundError(f"Go scraper executable not found")
    
    if not os.access(go_scraper_path, os.X_OK):
        os.chmod(go_scraper_path, 0o755)
    
    # Build command arguments
    cmd = [
        go_scraper_path,
        "-urls", ",".join(urls),
        "-proxy-type", proxy_type,
        "-timeout", str(timeout),
        "-max-retries", str(max_retries)
    ]
    
    # Add proxies if provided
    if proxies:
        cmd.extend(["-proxies", ",".join(proxies)])
    
    logger.info(f"Running Go scraper with {len(urls)} URLs")
    
    try:
        # Run the Go scraper and capture its output
        start_time = os.times()
        process = subprocess.run(cmd, capture_output=True, text=True, check=True)
        end_time = os.times()
        
        # Parse the JSON output
        result = json.loads(process.stdout)
        
        logger.info(f"Go scraper completed successfully in {end_time.elapsed - start_time.elapsed:.2f} seconds")
        logger.info(f"Scraped {result['total']} URLs. Success: {result['successful']}, Failed: {result['failed']}")
        
        return result
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Go scraper failed with exit code {e.returncode}")
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")
        
        # Return error result
        return {
            "results": [{"url": url, "error": f"Go scraper failed: {e.stderr}", "success": False} for url in urls],
            "total": len(urls),
            "successful": 0,
            "failed": len(urls),
            "total_time_seconds": 0,
            "proxy_type_used": proxy_type
        }
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Go scraper output: {e}")
        logger.error(f"Output: {process.stdout}")
        
        # Return error result
        return {
            "results": [{"url": url, "error": "Failed to parse Go scraper output", "success": False} for url in urls],
            "total": len(urls),
            "successful": 0,
            "failed": len(urls),
            "total_time_seconds": 0,
            "proxy_type_used": proxy_type
        }