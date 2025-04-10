from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, validator, root_validator
from typing import Dict, List, Any, Optional
import logging
import os
import time
from dotenv import load_dotenv
from app.go_bridge import scrape_with_go

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()


# Model for the request body - new format
class ScrapeRequest(BaseModel):
    datacenter: Optional[List[str]] = None
    residential: Optional[List[str]] = None
    mobile: Optional[List[str]] = None
    timeout: int = 5
    max_retries: int = 1

    @validator('timeout')
    def validate_timeout(cls, v):
        if v < 1:
            raise ValueError("Timeout must be at least 1 second")
        if v > 60:
            raise ValueError("Timeout cannot exceed 60 seconds")
        return v

    @validator('max_retries')
    def validate_max_retries(cls, v):
        if v < 0:
            raise ValueError("Max retries cannot be negative")
        if v > 10:
            raise ValueError("Max retries cannot exceed 10")
        return v

    @root_validator
    def validate_at_least_one_url_type(cls, values):
        # Check if at least one URL list is provided
        if not any(values.get(field) for field in ['datacenter', 'residential', 'mobile']):
            raise ValueError("At least one URL list must be provided")

        # Validate URL format for each list
        for field in ['datacenter', 'residential', 'mobile']:
            urls = values.get(field)
            if urls:
                for url in urls:
                    if not url.startswith(('http://', 'https://')):
                        raise ValueError(f"URL '{url}' in {field} must start with http:// or https://")

        return values


def get_proxy_list(proxy_type: str = "datacenter") -> List[str]:
    """Get proxies from the appropriate environment variable based on type."""
    env_var = f"{proxy_type.upper()}_PROXIES"
    proxies_str = os.getenv(env_var, "")
    if not proxies_str:
        logger.warning(f"No proxies configured in {env_var} environment variable.")
        return []

    # Split by comma
    proxies = [proxy.strip() for proxy in proxies_str.split(",") if proxy.strip()]
    logger.info(f"Loaded {len(proxies)} proxies of type {proxy_type}")
    return proxies


@app.post("/scrape")
async def scrape_urls(request: ScrapeRequest) -> Dict[str, Any]:
    """
    Scrape multiple URLs concurrently using the Go scraper.
    The request can contain URLs for different proxy types.
    """
    total_start_time = time.time()
    combined_results = {
        "results": [],
        "meta": {
            "total_urls": 0,
            "successful": 0,
            "failed": 0,
            "total_time_seconds": 0,
            "proxy_types_used": [],
            "python_overhead_seconds": 0
        },
        "proxy_type_details": {}
    }

    # Process each proxy type
    for proxy_type in ["datacenter", "residential", "mobile"]:
        urls = getattr(request, proxy_type, None)
        if not urls:
            continue

        logger.info(f"Processing {len(urls)} URLs for proxy type: {proxy_type}")
        combined_results["meta"]["total_urls"] += len(urls)
        combined_results["meta"]["proxy_types_used"].append(proxy_type)

        # Get proxies for this type
        proxies = get_proxy_list(proxy_type)

        # Start time for this batch
        batch_start_time = time.time()

        # Call the Go scraper through the bridge
        results = scrape_with_go(
            urls=urls,
            proxies=proxies,
            proxy_type=proxy_type,
            timeout=request.timeout,
            max_retries=request.max_retries
        )

        # Record batch time
        batch_time = time.time() - batch_start_time

        # Add results to combined results
        combined_results["results"].extend(results["results"])
        combined_results["meta"]["successful"] += results["successful"]
        combined_results["meta"]["failed"] += results["failed"]

        # Add proxy type specific details
        combined_results["proxy_type_details"][proxy_type] = {
            "urls_count": len(urls),
            "successful": results["successful"],
            "failed": results["failed"],
            "time_seconds": results["total_time_seconds"],
            "proxies_used_count": len(proxies)
        }

    # Calculate total time and overhead
    total_time = time.time() - total_start_time
    combined_results["meta"]["total_time_seconds"] = total_time

    # Calculate Python overhead (difference between total time and sum of Go scraper times)
    go_time = sum(details["time_seconds"] for details in combined_results["proxy_type_details"].values())
    combined_results["meta"]["python_overhead_seconds"] = max(0, total_time - go_time)

    logger.info(f"Total request processing time: {total_time:.2f} seconds")
    logger.info(f"Python overhead: {combined_results['meta']['python_overhead_seconds']:.2f} seconds")

    return combined_results


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": os.getenv("APP_VERSION", "0.1.0"),
        "go_scraper_exists": os.path.isfile(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "go-scraper", "go-scraper"))
    }