"""Extract module: API data fetching with retries, pagination, rate limiting"""

import logging
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class APIExtractor:
    """Handle API requests with retries, pagination, rate limiting, and auth."""
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        auth_header: str = "X-API-Key",
        timeout: int = 30,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        rate_limit_delay: float = 0.0,
    ):
        """
        Initialize API extractor.
        
        Args:
            base_url: Base URL for API
            api_key: API key for authentication
            auth_header: Header name for API key (default: X-API-Key)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            backoff_factor: Backoff multiplier for retries (e.g., 1.0 = 1s, 2s, 4s)
            rate_limit_delay: Delay between requests in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.auth_header = auth_header
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        
        # Configure session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        if self.api_key:
            self.session.headers.update({self.auth_header: self.api_key})
        
        logger.info(f"APIExtractor initialized: {base_url}")
    
    def fetch(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "GET",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Fetch data from API endpoint.
        
        Args:
            endpoint: API endpoint path
            params: Query parameters
            method: HTTP method
            **kwargs: Additional requests arguments
            
        Returns:
            JSON response as dictionary
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            logger.info(f"Fetching {method} {url} with params: {params}")
            
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                timeout=self.timeout,
                **kwargs
            )
            response.raise_for_status()
            
            # Rate limiting
            if self.rate_limit_delay > 0:
                time.sleep(self.rate_limit_delay)
            
            data = response.json()
            logger.info(f"Successfully fetched from {endpoint}")
            return data
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching {url}: {e}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error fetching {url}: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error from {url}: {e}")
            raise
    
    def fetch_paginated(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        page_param: str = "page",
        per_page_param: str = "per_page",
        per_page: int = 100,
        max_pages: Optional[int] = None,
        data_extractor: Optional[Callable[[Dict], List]] = None,
        has_more_checker: Optional[Callable[[Dict], bool]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch paginated data from API.
        
        Args:
            endpoint: API endpoint path
            params: Base query parameters
            page_param: Query parameter name for page number
            per_page_param: Query parameter name for items per page
            per_page: Items per page
            max_pages: Maximum pages to fetch (None = all)
            data_extractor: Function to extract records from response (default: response['data'])
            has_more_checker: Function to check if more pages exist (default: checks if data empty)
            
        Returns:
            List of all fetched records
        """
        params = params or {}
        all_records = []
        page = 1
        
        # Default extractors
        if data_extractor is None:
            data_extractor = lambda r: r.get('data', [])
        if has_more_checker is None:
            has_more_checker = lambda r: len(data_extractor(r)) > 0
        
        while True:
            # Update pagination params
            params[page_param] = page
            params[per_page_param] = per_page
            
            logger.info(f"Fetching page {page} from {endpoint}")
            response = self.fetch(endpoint, params=params)
            
            # Extract records
            records = data_extractor(response)
            if not records:
                logger.info(f"No more records at page {page}")
                break
            
            all_records.extend(records)
            logger.info(f"Page {page}: fetched {len(records)} records (total: {len(all_records)})")
            
            # Check if more pages exist
            if not has_more_checker(response):
                logger.info("No more pages available")
                break
            
            # Check max pages limit
            if max_pages and page >= max_pages:
                logger.info(f"Reached max_pages limit: {max_pages}")
                break
            
            page += 1
        
        logger.info(f"Pagination complete: {len(all_records)} total records from {page} pages")
        return all_records
    
    def fetch_offset_paginated(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        offset_param: str = "offset",
        limit_param: str = "limit",
        limit: int = 100,
        max_records: Optional[int] = None,
        data_extractor: Optional[Callable[[Dict], List]] = None,
        total_extractor: Optional[Callable[[Dict], int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch paginated data using offset-based pagination.
        
        Args:
            endpoint: API endpoint path
            params: Base query parameters
            offset_param: Query parameter name for offset (default: 'offset')
            limit_param: Query parameter name for limit (default: 'limit')
            limit: Records per request (default: 100)
            max_records: Maximum records to fetch (None = all available)
            data_extractor: Function to extract records from response (default: response['data'])
            total_extractor: Function to extract total count (default: response['pagination']['total'])
            
        Returns:
            List of all fetched records
        """
        params = params or {}
        all_records = []
        offset = 0
        
        # Default extractors
        if data_extractor is None:
            data_extractor = lambda r: r.get('data', [])
        if total_extractor is None:
            total_extractor = lambda r: r.get('pagination', {}).get('total', 0)
        
        # First request to get total count
        params[offset_param] = offset
        params[limit_param] = limit
        
        logger.info(f"Starting offset pagination for {endpoint}")
        response = self.fetch(endpoint, params=params)
        
        total_available = total_extractor(response)
        target_records = min(total_available, max_records) if max_records else total_available
        
        logger.info(f"Total available: {total_available}, Target: {target_records}")
        
        # Extract first batch
        records = data_extractor(response)
        all_records.extend(records)
        logger.info(f"Offset {offset}: fetched {len(records)} records (total: {len(all_records)}/{target_records})")
        
        # Continue fetching
        while len(all_records) < target_records:
            offset += limit
            params[offset_param] = offset
            
            logger.info(f"Fetching offset {offset}")
            response = self.fetch(endpoint, params=params)
            
            records = data_extractor(response)
            if not records:
                logger.info(f"No more records at offset {offset}")
                break
            
            all_records.extend(records)
            logger.info(f"Offset {offset}: fetched {len(records)} records (total: {len(all_records)}/{target_records})")
            
            # Check if we've reached our target
            if len(all_records) >= target_records:
                # Trim to exact target if we overfetched
                all_records = all_records[:target_records]
                break
        
        logger.info(f"Offset pagination complete: {len(all_records)} total records")
        return all_records


def save_raw_data(data: Any, filepath: str, create_dirs: bool = True) -> None:
    """
    Save raw data to JSON file with metadata.
    
    Args:
        data: Data to save
        filepath: Path to save file
        create_dirs: Create parent directories if missing
    """
    path = Path(filepath)
    
    if create_dirs:
        path.parent.mkdir(parents=True, exist_ok=True)
    
    # Add metadata wrapper
    output = {
        'extracted_at': datetime.now().isoformat(),
        'record_count': len(data) if isinstance(data, list) else 1,
        'data': data
    }
    
    with path.open('w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved raw data to {filepath}")


