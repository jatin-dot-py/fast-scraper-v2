from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
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

# Model for the request body
class ScrapeRequest(BaseModel):
    urls: List[str]
    proxy_type: str = "datacenter"  # Default to datacenter proxies
    timeout: int = 10
    max_retries: int = 3

def get_proxy_list() -> List[str]:
    """Get datacenter proxies from environment variable."""
    proxies_str = os.getenv("DATACENTER_PROXIES", "")
    if not proxies_str:
        logger.warning("No proxies configured in DATACENTER_PROXIES environment variable.")
        return []
    
    # Split by comma
    return [proxy.strip() for proxy in proxies_str.split(",") if proxy.strip()]

@app.post("/scrape")
async def scrape_urls(request: ScrapeRequest) -> Dict[str, Any]:
    """Scrape multiple URLs concurrently using the Go scraper."""
    if not request.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")
    
    start_time = time.time()
    
    # Get proxies
    proxies = get_proxy_list()
    proxy_count = len(proxies)
    
    logger.info(f"Scraping {len(request.urls)} URLs using {proxy_count} datacenter proxies")
    
    # Call the Go scraper through the bridge
    results = scrape_with_go(
        urls=request.urls,
        proxies=proxies,
        proxy_type="datacenter",  # Always use datacenter
        timeout=request.timeout,
        max_retries=request.max_retries
    )
    
    total_time = time.time() - start_time
    logger.info(f"Total request time including Python overhead: {total_time:.2f} seconds")
    
    # Add Python overhead timing
    results["python_overhead_seconds"] = total_time - results.get("total_time_seconds", 0)
    
    return results

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": os.getenv("APP_VERSION", "0.1.0")}