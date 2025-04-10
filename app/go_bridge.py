import json
import logging
import os
import subprocess
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def scrape_with_go(urls: List[str], proxies: Optional[List[str]] = None, proxy_type: str = "datacenter",
                   timeout: int = 10, max_retries: int = 3) -> Dict[str, Any]:
    """
    Uses the Go scraper executable to scrape URLs concurrently.

    Args:
        urls: List of URLs to scrape
        proxies: List of proxy URLs to use
        proxy_type: Type of proxies (datacenter, residential, etc.)
        timeout: Timeout in seconds for each request
        max_retries: Maximum number of retries for each URL

    Returns:
        Dictionary with detailed scraping results
    """
    if not urls:
        logger.warning("No URLs provided to scrape_with_go")
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
        error_msg = f"Go scraper executable not found at {go_scraper_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    if not os.access(go_scraper_path, os.X_OK):
        logger.info(f"Setting executable permissions on {go_scraper_path}")
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
        # Log the number of proxies without exposing credentials
        logger.info(f"Using {len(proxies)} proxies of type {proxy_type}")
        cmd.extend(["-proxies", ",".join(proxies)])
    else:
        logger.warning(f"No proxies provided for {len(urls)} URLs")

    logger.info(f"Running Go scraper with {len(urls)} URLs, timeout={timeout}s, max_retries={max_retries}")

    process = None
    start_time = os.times()

    try:
        # Run the Go scraper and capture its output
        logger.debug(f"Executing command: {' '.join(cmd)}")
        process = subprocess.run(cmd, capture_output=True, text=True, check=True)
        end_time = os.times()

        # Parse the JSON output
        result = json.loads(process.stdout)

        elapsed_time = end_time.elapsed - start_time.elapsed
        logger.info(f"Go scraper completed successfully in {elapsed_time:.2f} seconds")
        logger.info(f"Scraped {result['total']} URLs. Success: {result['successful']}, Failed: {result['failed']}")

        return result

    except subprocess.CalledProcessError as e:
        logger.error(f"Go scraper failed with exit code {e.returncode}")
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")

        # Return detailed error result
        end_time = os.times()
        elapsed_time = end_time.elapsed - start_time.elapsed

        # Create a detailed error result for each URL
        error_results = []
        for url in urls:
            error_results.append({
                "url": url,
                "error": f"Go scraper process failed with code {e.returncode}",
                "detailed_error": f"STDOUT: {e.stdout}\nSTDERR: {e.stderr}\nCommand: {' '.join(cmd)}",
                "success": False,
                "proxy_used": proxy_type,
                "attempts_made": 0,
                "elapsed_seconds": elapsed_time / len(urls)  # Approximate time per URL
            })

        return {
            "results": error_results,
            "total": len(urls),
            "successful": 0,
            "failed": len(urls),
            "total_time_seconds": elapsed_time,
            "proxy_type_used": proxy_type
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Go scraper output: {e}")
        if process:
            logger.error(f"Output: {process.stdout}")

        # Return detailed error result for JSON parse failure
        end_time = os.times()
        elapsed_time = end_time.elapsed - start_time.elapsed

        error_results = []
        for url in urls:
            stdout_snippet = process.stdout[:1000] + "..." if process and len(process.stdout) > 1000 else (
                process.stdout if process else "None")

            error_results.append({
                "url": url,
                "error": "Failed to parse Go scraper output",
                "detailed_error": f"JSON Parse Error: {str(e)}\nOutput (truncated): {stdout_snippet}",
                "success": False,
                "proxy_used": proxy_type,
                "attempts_made": 0,
                "elapsed_seconds": elapsed_time / len(urls)  # Approximate time per URL
            })

        return {
            "results": error_results,
            "total": len(urls),
            "successful": 0,
            "failed": len(urls),
            "total_time_seconds": elapsed_time,
            "proxy_type_used": proxy_type
        }