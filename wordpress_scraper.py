#!/usr/bin/env python3
"""
WordPress Scraper with Cloudflare Bypass
-----------------------------------------
A Scrapy-based scraper that handles Cloudflare-protected Publicly avaialble WordPress sites.
Exports data to JSON with descriptive error handling.

Usage:
    python wordpress_scraper.py <url>
    python wordpress_scraper.py https://example.com

Output:
    Creates a JSON file named 'output_<timestamp>.json'
"""

import sys
import json
import logging
from datetime import datetime
from urllib.parse import urlparse
from typing import Optional, Dict, Any, Generator

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.http import Response, Request
from scrapy.exceptions import CloseSpider
from scrapy import signals


class ScraperError(Exception):
    """Custom exception for scraper-specific errors."""
    pass


class WordPressSpider(scrapy.Spider):
    """
    Spider for scraping WordPress sites with Cloudflare protection.
    
    Extracts:
    - Page title
    - Meta description
    - All text content
    - Links
    - Images
    - WordPress-specific data (posts, categories, etc.)
    """
    
    name = 'wordpress_spider'
    
    # WordPress-specific selectors
    WP_SELECTORS = {
        'post_title': ['h1.entry-title', 'h1.post-title', '.entry-header h1', 'article h1'],
        'post_content': ['.entry-content', '.post-content', 'article .content', '.single-content'],
        'post_meta': ['.entry-meta', '.post-meta', '.byline'],
        'categories': ['.cat-links a', '.post-categories a', '.entry-categories a'],
        'tags': ['.tag-links a', '.post-tags a', '.entry-tags a'],
        'author': ['.author-name', '.entry-author', '.post-author a'],
        'date': ['.entry-date', '.post-date', 'time.published'],
        'comments': ['.comments-area', '#comments', '.comment-list'],
    }
    
    def __init__(self, url: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_url = url
        self.start_urls = [url]
        self.scraped_data = []
        self.errors = []
        
        # Validate URL
        self._validate_url(url)
    
    def _validate_url(self, url: str) -> None:
        """Validate the provided URL format."""
        try:
            result = urlparse(url)
            if not all([result.scheme, result.netloc]):
                raise ScraperError(
                    f"Invalid URL format: '{url}'. "
                    "URL must include scheme (http/https) and domain. "
                    "Example: https://example.com"
                )
            if result.scheme not in ['http', 'https']:
                raise ScraperError(
                    f"Invalid URL scheme: '{result.scheme}'. "
                    "Only 'http' and 'https' schemes are supported."
                )
        except ValueError as e:
            raise ScraperError(f"URL parsing error: {str(e)}")
    
    def start_requests(self) -> Generator[Request, None, None]:
        """Generate initial requests with error handling."""
        for url in self.start_urls:
            self.logger.info(f"Starting scrape of: {url}")
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.handle_error,
                meta={
                    'dont_redirect': False,
                    'handle_httpstatus_list': [403, 503, 520, 521, 522, 523, 524],
                }
            )
    
    def handle_error(self, failure) -> None:
        """Handle request failures with descriptive error messages."""
        request = failure.request
        
        error_info = {
            'url': request.url,
            'timestamp': datetime.now().isoformat(),
            'error_type': failure.type.__name__ if failure.type else 'Unknown',
        }
        
        # Provide descriptive error messages based on failure type
        if failure.check(scrapy.exceptions.IgnoreRequest):
            error_info['message'] = "Request was ignored by middleware or duplicate filter."
            error_info['suggestion'] = "Check if URL is accessible and not blocked by robots.txt."
        
        elif failure.check(Exception):
            error_type = failure.type.__name__
            
            if 'DNSLookupError' in error_type:
                error_info['message'] = f"DNS lookup failed for domain."
                error_info['suggestion'] = (
                    "1. Check if the domain name is spelled correctly.\n"
                    "2. Verify your internet connection.\n"
                    "3. The website might be down or doesn't exist."
                )
            
            elif 'TimeoutError' in error_type or 'TCPTimedOut' in error_type:
                error_info['message'] = "Connection timed out while trying to reach the server."
                error_info['suggestion'] = (
                    "1. The server might be slow or overloaded.\n"
                    "2. Try increasing the timeout in settings.\n"
                    "3. Check if the website is accessible from a browser."
                )
            
            elif 'ConnectionRefused' in error_type:
                error_info['message'] = "Connection was refused by the server."
                error_info['suggestion'] = (
                    "1. The server might be down.\n"
                    "2. The port might be blocked.\n"
                    "3. Firewall might be blocking the connection."
                )
            
            elif 'SSLError' in error_type:
                error_info['message'] = "SSL/TLS certificate verification failed."
                error_info['suggestion'] = (
                    "1. The site's SSL certificate might be expired or invalid.\n"
                    "2. Your system's CA certificates might be outdated.\n"
                    "3. Consider using ROBOTSTXT_OBEY = False if appropriate."
                )
            
            else:
                error_info['message'] = f"Request failed: {failure.getErrorMessage()}"
                error_info['suggestion'] = "Check the error details and try again."
        
        self.errors.append(error_info)
        self.logger.error(
            f"\n{'='*60}\n"
            f"SCRAPING ERROR\n"
            f"{'='*60}\n"
            f"URL: {error_info['url']}\n"
            f"Error Type: {error_info['error_type']}\n"
            f"Message: {error_info['message']}\n"
            f"Suggestion: {error_info['suggestion']}\n"
            f"{'='*60}"
        )
    
    def parse(self, response: Response) -> Generator[Dict[str, Any], None, None]:
        """Parse the response and extract WordPress content."""
        
        # Check for Cloudflare challenge pages
        if self._is_cloudflare_challenge(response):
            self.logger.warning(
                f"\n{'='*60}\n"
                f"CLOUDFLARE PROTECTION DETECTED\n"
                f"{'='*60}\n"
                f"URL: {response.url}\n"
                f"Status: {response.status}\n"
                f"The site is protected by Cloudflare's anti-bot measures.\n"
                f"Suggestions:\n"
                f"  1. Use cloudscraper library instead\n"
                f"  2. Use a headless browser (Playwright/Selenium)\n"
                f"  3. Use rotating proxies\n"
                f"  4. Add delays between requests\n"
                f"{'='*60}"
            )
            self.errors.append({
                'url': response.url,
                'error_type': 'CloudflareProtection',
                'message': 'Cloudflare anti-bot challenge detected',
                'status_code': response.status,
                'timestamp': datetime.now().isoformat(),
            })
            return
        
        # Check for HTTP errors
        if response.status >= 400:
            self._handle_http_error(response)
            return
        
        # Extract data
        try:
            data = self._extract_page_data(response)
            self.scraped_data.append(data)
            yield data
            
        except Exception as e:
            error_info = {
                'url': response.url,
                'error_type': 'ExtractionError',
                'message': f"Failed to extract data: {str(e)}",
                'timestamp': datetime.now().isoformat(),
            }
            self.errors.append(error_info)
            self.logger.error(f"Extraction error: {str(e)}")
    
    def _is_cloudflare_challenge(self, response: Response) -> bool:
        """Detect if response is a Cloudflare challenge page."""
        cloudflare_indicators = [
            'cf-browser-verification',
            'cloudflare',
            'cf_clearance',
            'Checking your browser',
            'DDoS protection by Cloudflare',
            'ray ID',
        ]
        
        body_text = response.text.lower() if response.text else ''
        
        # Check status codes commonly used by Cloudflare
        if response.status in [503, 520, 521, 522, 523, 524]:
            return True
        
        # Check for Cloudflare indicators in body
        for indicator in cloudflare_indicators:
            if indicator.lower() in body_text:
                return True
        
        # Check headers
        server_header = response.headers.get('Server', b'').decode('utf-8', errors='ignore')
        if 'cloudflare' in server_header.lower():
            cf_ray = response.headers.get('CF-RAY', None)
            if cf_ray and response.status >= 400:
                return True
        
        return False
    
    def _handle_http_error(self, response: Response) -> None:
        """Handle HTTP error responses with descriptive messages."""
        status = response.status
        
        error_messages = {
            400: ("Bad Request", "The server couldn't understand the request. Check URL format."),
            401: ("Unauthorized", "Authentication required. The page might need login credentials."),
            403: ("Forbidden", "Access denied. The server refuses to fulfill the request."),
            404: ("Not Found", "The requested page doesn't exist. Check if the URL is correct."),
            429: ("Too Many Requests", "Rate limited. Add delays between requests."),
            500: ("Internal Server Error", "Server-side error. The website might be experiencing issues."),
            502: ("Bad Gateway", "The server received an invalid response. Try again later."),
            503: ("Service Unavailable", "Server temporarily unavailable. Could be maintenance or overload."),
        }
        
        error_name, suggestion = error_messages.get(
            status, 
            (f"HTTP Error {status}", "Unexpected HTTP error occurred.")
        )
        
        error_info = {
            'url': response.url,
            'error_type': 'HTTPError',
            'status_code': status,
            'message': error_name,
            'suggestion': suggestion,
            'timestamp': datetime.now().isoformat(),
        }
        
        self.errors.append(error_info)
        self.logger.error(
            f"\n{'='*60}\n"
            f"HTTP ERROR\n"
            f"{'='*60}\n"
            f"URL: {response.url}\n"
            f"Status Code: {status}\n"
            f"Error: {error_name}\n"
            f"Suggestion: {suggestion}\n"
            f"{'='*60}"
        )
    
    def _extract_page_data(self, response: Response) -> Dict[str, Any]:
        """Extract all relevant data from the page."""
        data = {
            'url': response.url,
            'scraped_at': datetime.now().isoformat(),
            'status_code': response.status,
            'basic_info': self._extract_basic_info(response),
            'wordpress_content': self._extract_wordpress_content(response),
            'links': self._extract_links(response),
            'images': self._extract_images(response),
            'meta_data': self._extract_meta_data(response),
        }
        
        self.logger.info(f"Successfully extracted data from: {response.url}")
        return data
    
    def _extract_basic_info(self, response: Response) -> Dict[str, Any]:
        """Extract basic page information."""
        return {
            'title': response.css('title::text').get('').strip(),
            'h1': response.css('h1::text').getall(),
            'description': response.css('meta[name="description"]::attr(content)').get(''),
            'canonical_url': response.css('link[rel="canonical"]::attr(href)').get(''),
            'language': response.css('html::attr(lang)').get(''),
        }
    
    def _extract_wordpress_content(self, response: Response) -> Dict[str, Any]:
        """Extract WordPress-specific content."""
        wp_content = {}
        
        for field, selectors in self.WP_SELECTORS.items():
            for selector in selectors:
                content = response.css(f'{selector}::text').getall()
                if content:
                    wp_content[field] = [c.strip() for c in content if c.strip()]
                    break
            else:
                wp_content[field] = []
        
        # Extract main content text
        content_selectors = self.WP_SELECTORS['post_content']
        for selector in content_selectors:
            main_content = response.css(selector).get()
            if main_content:
                # Get text content, removing HTML tags
                from scrapy.selector import Selector
                content_text = Selector(text=main_content).css('*::text').getall()
                wp_content['main_content_text'] = ' '.join(
                    [t.strip() for t in content_text if t.strip()]
                )
                break
        
        # Check if it's a WordPress site
        wp_content['is_wordpress'] = self._detect_wordpress(response)
        
        return wp_content
    
    def _detect_wordpress(self, response: Response) -> bool:
        """Detect if the site is running WordPress."""
        wp_indicators = [
            'wp-content',
            'wp-includes',
            'wp-json',
            'wordpress',
            '/wp-admin',
        ]
        
        body = response.text.lower() if response.text else ''
        return any(indicator in body for indicator in wp_indicators)
    
    def _extract_links(self, response: Response) -> list:
        """Extract all links from the page."""
        links = []
        for link in response.css('a[href]'):
            href = link.css('::attr(href)').get()
            text = link.css('::text').get('').strip()
            if href:
                links.append({
                    'url': response.urljoin(href),
                    'text': text,
                })
        return links[:100]  # Limit to 100 links
    
    def _extract_images(self, response: Response) -> list:
        """Extract all images from the page."""
        images = []
        for img in response.css('img'):
            src = img.css('::attr(src)').get()
            alt = img.css('::attr(alt)').get('')
            if src:
                images.append({
                    'url': response.urljoin(src),
                    'alt': alt,
                })
        return images[:50]  # Limit to 50 images
    
    def _extract_meta_data(self, response: Response) -> Dict[str, Any]:
        """Extract meta tags and Open Graph data."""
        meta = {}
        
        # Standard meta tags
        for tag in response.css('meta'):
            name = tag.css('::attr(name)').get() or tag.css('::attr(property)').get()
            content = tag.css('::attr(content)').get()
            if name and content:
                meta[name] = content
        
        return meta


def run_scraper(url: str, output_file: Optional[str] = None) -> Dict[str, Any]:
    """
    Run the WordPress scraper on a given URL.
    
    Args:
        url: The URL to scrape
        output_file: Optional output filename (defaults to timestamped name)
    
    Returns:
        Dictionary containing scraped data and any errors
    """
    
    if not output_file:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'output_{timestamp}.json'
    
    # Configure Scrapy settings
    settings = {
        'LOG_LEVEL': 'INFO',
        'ROBOTSTXT_OBEY': False,  # Disable for testing, enable in production
        'CONCURRENT_REQUESTS': 1,
        'DOWNLOAD_DELAY': 2,
        'COOKIES_ENABLED': True,
        'RETRY_TIMES': 3,
        'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429],
        'DOWNLOAD_TIMEOUT': 30,
        
        # User agent rotation
        'USER_AGENT': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ),
        
        # Cloudflare bypass settings
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
            'scrapy.downloadermiddlewares.retry.RetryMiddleware': 90,
        },
        
        # Additional headers
        'DEFAULT_REQUEST_HEADERS': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        },
        
        # Disable Scrapy's feed export, we'll handle it manually
        'FEEDS': {},
    }
    
    # Store results
    results = {
        'url': url,
        'started_at': datetime.now().isoformat(),
        'data': [],
        'errors': [],
    }
    
    # Create spider instance to access data after crawl
    spider_instance = None
    
    def spider_closed(spider):
        nonlocal spider_instance
        spider_instance = spider
    
    # Run the crawler
    process = CrawlerProcess(settings)
    crawler = process.create_crawler(WordPressSpider)
    crawler.signals.connect(spider_closed, signal=signals.spider_closed)
    
    try:
        process.crawl(crawler, url=url)
        process.start()
        
        # Collect results from spider
        if spider_instance:
            results['data'] = spider_instance.scraped_data
            results['errors'] = spider_instance.errors
        
    except Exception as e:
        error_info = {
            'error_type': 'CrawlerError',
            'message': f"Crawler failed to start: {str(e)}",
            'suggestion': "Check if the URL is valid and accessible.",
            'timestamp': datetime.now().isoformat(),
        }
        results['errors'].append(error_info)
        print(f"\n{'='*60}")
        print("CRAWLER ERROR")
        print(f"{'='*60}")
        print(f"Error: {str(e)}")
        print(f"{'='*60}\n")
    
    results['finished_at'] = datetime.now().isoformat()
    results['success'] = len(results['data']) > 0 and len(results['errors']) == 0
    
    # Save to JSON file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n{'='*60}")
        print("SCRAPING COMPLETE")
        print(f"{'='*60}")
        print(f"Output saved to: {output_file}")
        print(f"Pages scraped: {len(results['data'])}")
        print(f"Errors encountered: {len(results['errors'])}")
        print(f"{'='*60}\n")
        
    except IOError as e:
        print(f"\n{'='*60}")
        print("FILE WRITE ERROR")
        print(f"{'='*60}")
        print(f"Failed to write output file: {str(e)}")
        print(f"Suggestion: Check file permissions and disk space.")
        print(f"{'='*60}\n")
    
    return results


def main():
    """Main entry point with argument parsing and validation."""
    
    print("""
╔═══════════════════════════════════════════════════════════╗
║         WordPress Scraper with Cloudflare Bypass          ║
╠═══════════════════════════════════════════════════════════╣
║  Extracts content from WordPress sites protected by       ║
║  Cloudflare and exports to JSON format.                   ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Check command line arguments
    if len(sys.argv) < 2:
        print("""
ERROR: No URL provided!

Usage:
    python wordpress_scraper.py <url> [output_file]

Examples:
    python wordpress_scraper.py https://example.com
    python wordpress_scraper.py https://example.com/blog output.json

Arguments:
    url          - The URL to scrape (required)
    output_file  - Output JSON filename (optional, defaults to output_<timestamp>.json)
        """)
        sys.exit(1)
    
    url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Validate URL format before starting
    try:
        parsed = urlparse(url)
        if not parsed.scheme:
            print(f"""
ERROR: Invalid URL - missing scheme (http/https)

Provided URL: {url}
Suggestion: Add 'https://' prefix

Example: https://{url}
            """)
            sys.exit(1)
        
        if not parsed.netloc:
            print(f"""
ERROR: Invalid URL - missing domain

Provided URL: {url}
Suggestion: Ensure the URL includes a valid domain name

Example: https://example.com/page
            """)
            sys.exit(1)
            
    except Exception as e:
        print(f"""
ERROR: Failed to parse URL

Provided URL: {url}
Error: {str(e)}
Suggestion: Ensure the URL is properly formatted
        """)
        sys.exit(1)
    
    print(f"Target URL: {url}")
    print(f"Output file: {output_file or 'auto-generated'}")
    print("-" * 60)
    
    # Run the scraper
    results = run_scraper(url, output_file)
    
    # Exit with appropriate code
    if results['success']:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
