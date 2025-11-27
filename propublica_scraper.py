#!/usr/bin/env python3
"""
PropPublica PPP Loan Scraper
----------------------------
A Scrapy-based scraper specifically designed for the PropPublica
Coronavirus Bailouts/PPP Loan database.

Usage:
    python propublica_scraper.py <url>
    python propublica_scraper.py "https://projects.propublica.org/coronavirus/bailouts/search?q=90210+medical&v=1"

Output:
    Creates a JSON file named 'loans_<timestamp>.json'
"""

import sys
import json
import re
import logging
from datetime import datetime
from urllib.parse import urlparse, urljoin
from typing import Optional, Dict, Any, List, Generator

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.http import Response, Request
from scrapy import signals


class PropublicaLoanSpider(scrapy.Spider):
    """
    Spider for scraping PPP Loan data from PropPublica.
    
    Extracts:
    - Recipient name
    - Location (city, state)
    - Loan status
    - Loan amount
    - Date approved
    - Detail page URL
    """
    
    name = 'propublica_loan_spider'
    
    def __init__(self, url: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_url = url
        self.start_urls = [url]
        self.scraped_loans = []
        self.errors = []
    
    def start_requests(self) -> Generator[Request, None, None]:
        """Generate initial requests."""
        for url in self.start_urls:
            self.logger.info(f"Starting scrape of: {url}")
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.handle_error,
                headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
    
    def handle_error(self, failure) -> None:
        """Handle request failures with descriptive error messages."""
        request = failure.request
        error_info = {
            'url': request.url,
            'timestamp': datetime.now().isoformat(),
            'error_type': failure.type.__name__ if failure.type else 'Unknown',
            'message': str(failure.getErrorMessage()),
        }
        self.errors.append(error_info)
        self.logger.error(f"Request failed: {error_info}")
    
    def parse(self, response: Response) -> Generator[Dict[str, Any], None, None]:
        """Parse the search results page and extract loan data."""
        
        self.logger.info(f"Parsing response from: {response.url}")
        self.logger.info(f"Response status: {response.status}")
        self.logger.info(f"Response length: {len(response.text)} bytes")
        
        # Check for HTTP errors
        if response.status >= 400:
            self.errors.append({
                'url': response.url,
                'error_type': 'HTTPError',
                'status_code': response.status,
                'message': f'HTTP {response.status} error',
                'timestamp': datetime.now().isoformat(),
            })
            self.logger.error(f"HTTP Error {response.status} for {response.url}")
            return
        
        # Extract the search query info
        search_info = self._extract_search_info(response)
        
        # Find all loan entries - they are in <li> elements with specific structure
        # Looking at the HTML: <li class="list pt3 pb5-l pb4 w-100">
        loan_items = response.css('li.list.pt3')
        
        self.logger.info(f"Found {len(loan_items)} loan entries")
        
        if not loan_items:
            # Try alternative selectors
            loan_items = response.css('ul > li.list')
            self.logger.info(f"Alternative selector found {len(loan_items)} entries")
        
        if not loan_items:
            self.logger.warning("No loan entries found! Page structure may have changed.")
            self.logger.debug(f"Page content preview: {response.text[:2000]}")
            self.errors.append({
                'url': response.url,
                'error_type': 'NoDataFound',
                'message': 'No loan entries found on page. The page structure may have changed.',
                'timestamp': datetime.now().isoformat(),
            })
            return
        
        for idx, item in enumerate(loan_items):
            try:
                loan_data = self._extract_loan_data(item, response, idx)
                if loan_data and loan_data.get('recipient'):
                    self.scraped_loans.append(loan_data)
                    yield loan_data
            except Exception as e:
                self.logger.error(f"Error extracting loan {idx}: {str(e)}")
                self.errors.append({
                    'error_type': 'ExtractionError',
                    'message': f'Failed to extract loan {idx}: {str(e)}',
                    'timestamp': datetime.now().isoformat(),
                })
        
        self.logger.info(f"Successfully extracted {len(self.scraped_loans)} loans")
    
    def _extract_search_info(self, response: Response) -> Dict[str, Any]:
        """Extract search query information from the page."""
        search_value = response.css('input[name="q"]::attr(value)').get('')
        result_header = response.css('h1::text').get('')
        
        return {
            'search_query': search_value,
            'result_header': result_header.strip() if result_header else '',
        }
    
    def _extract_loan_data(self, item, response: Response, index: int) -> Dict[str, Any]:
        """Extract loan data from a single list item."""
        
        # Get all divs with class f7 (labels) and f5 tiempos-text (values)
        labels = item.css('div.f7::text').getall()
        labels = [l.strip() for l in labels if l.strip()]
        
        # Recipient name and URL
        recipient_link = item.css('div.tiempos-text.lh-title a')
        recipient_name = recipient_link.css('::text').get('').strip()
        recipient_url = recipient_link.css('::attr(href)').get('')
        if recipient_url:
            recipient_url = urljoin(response.url, recipient_url)
        
        # Get all value divs
        value_divs = item.css('div.f5.tiempos-text')
        
        # Extract location (first value after recipient in the flex container)
        location = ''
        loan_status = ''
        loan_amount = ''
        date_approved = ''
        
        # Find the flex container with the details
        flex_container = item.css('div.flex.flex-wrap')
        if flex_container:
            detail_blocks = flex_container.css('div.f6, div.w-25-l, div.w-15-l')
            
            for block in flex_container.css('div[class*="w-"]'):
                label = block.css('div.f7::text').get('').strip()
                value = block.css('div.f5.tiempos-text::text').get('')
                if value:
                    value = value.strip()
                
                if 'Location' in label:
                    location = value
                elif 'Loan Status' in label:
                    loan_status = value
                elif 'Loan Amount' in label:
                    loan_amount = value
                elif 'Date Approved' in label:
                    date_approved = value
        
        # Alternative extraction if flex container parsing didn't work
        if not location and not loan_amount:
            # Get all text values after the recipient
            all_values = item.css('div.f5.tiempos-text::text').getall()
            all_values = [v.strip() for v in all_values if v.strip()]
            
            # Skip the first one if it's the recipient (might have text directly)
            for val in all_values:
                if not location and ',' in val and len(val.split(',')) == 2:
                    # Looks like "City, ST" format
                    location = val
                elif not loan_amount and val.startswith('$'):
                    loan_amount = val
                elif not loan_status and ('Forgiven' in val or 'Active' in val or 'Paid' in val):
                    loan_status = val
                elif not date_approved and any(month in val for month in 
                    ['Jan', 'Feb', 'March', 'April', 'May', 'June', 'July', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec']):
                    date_approved = val
        
        loan_data = {
            'index': index + 1,
            'recipient': recipient_name,
            'detail_url': recipient_url,
            'location': location,
            'loan_status': loan_status,
            'loan_amount': loan_amount,
            'loan_amount_numeric': self._parse_amount(loan_amount),
            'date_approved': date_approved,
            'scraped_at': datetime.now().isoformat(),
        }
        
        return loan_data
    
    def _parse_amount(self, amount_str: str) -> Optional[float]:
        """Parse loan amount string to numeric value."""
        if not amount_str:
            return None
        try:
            # Remove $, commas, and whitespace
            cleaned = re.sub(r'[$,\s]', '', amount_str)
            return float(cleaned)
        except (ValueError, TypeError):
            return None


def run_scraper(url: str, output_file: Optional[str] = None) -> Dict[str, Any]:
    """
    Run the PropPublica loan scraper on a given URL.
    
    Args:
        url: The URL to scrape
        output_file: Optional output filename (defaults to timestamped name)
    
    Returns:
        Dictionary containing scraped data and any errors
    """
    
    if not output_file:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'loans_{timestamp}.json'
    
    # Configure Scrapy settings
    settings = {
        'LOG_LEVEL': 'INFO',
        'ROBOTSTXT_OBEY': False,
        'CONCURRENT_REQUESTS': 1,
        'DOWNLOAD_DELAY': 1,
        'COOKIES_ENABLED': True,
        'RETRY_TIMES': 3,
        'DOWNLOAD_TIMEOUT': 30,
        
        'USER_AGENT': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ),
        
        'DEFAULT_REQUEST_HEADERS': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        },
        
        'FEEDS': {},
    }
    
    results = {
        'url': url,
        'started_at': datetime.now().isoformat(),
        'loans': [],
        'errors': [],
        'total_loans': 0,
    }
    
    spider_instance = None
    
    def spider_closed(spider):
        nonlocal spider_instance
        spider_instance = spider
    
    process = CrawlerProcess(settings)
    crawler = process.create_crawler(PropublicaLoanSpider)
    crawler.signals.connect(spider_closed, signal=signals.spider_closed)
    
    try:
        process.crawl(crawler, url=url)
        process.start()
        
        if spider_instance:
            results['loans'] = spider_instance.scraped_loans
            results['errors'] = spider_instance.errors
            results['total_loans'] = len(spider_instance.scraped_loans)
        
    except Exception as e:
        error_info = {
            'error_type': 'CrawlerError',
            'message': f"Crawler failed: {str(e)}",
            'timestamp': datetime.now().isoformat(),
        }
        results['errors'].append(error_info)
        print(f"\n{'='*60}")
        print("CRAWLER ERROR")
        print(f"{'='*60}")
        print(f"Error: {str(e)}")
        print(f"{'='*60}\n")
    
    results['finished_at'] = datetime.now().isoformat()
    results['success'] = len(results['loans']) > 0
    
    # Save to JSON file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*60}")
        print("SCRAPING COMPLETE")
        print(f"{'='*60}")
        print(f"Output saved to: {output_file}")
        print(f"Total loans scraped: {results['total_loans']}")
        print(f"Errors: {len(results['errors'])}")
        
        if results['loans']:
            print(f"\nFirst 3 loans:")
            for loan in results['loans'][:3]:
                print(f"  - {loan['recipient']}: {loan['loan_amount']} ({loan['location']})")
        
        print(f"{'='*60}\n")
        
    except IOError as e:
        print(f"\nFailed to write output file: {str(e)}")
    
    return results


def main():
    """Main entry point."""
    
    print("""
╔═══════════════════════════════════════════════════════════╗
║           PropPublica PPP Loan Scraper                    ║
╠═══════════════════════════════════════════════════════════╣
║  Extracts PPP loan data from PropPublica's coronavirus    ║
║  bailout database and exports to JSON format.             ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    if len(sys.argv) < 2:
        # Default to the URL from README
        url = "https://projects.propublica.org/coronavirus/bailouts/search?q=90210+medical&v=1"
        print(f"No URL provided, using default: {url}")
    else:
        url = sys.argv[1]
    
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Validate URL
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            print(f"ERROR: Invalid URL format: {url}")
            print("Example: https://projects.propublica.org/coronavirus/bailouts/search?q=90210")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to parse URL: {str(e)}")
        sys.exit(1)
    
    print(f"Target URL: {url}")
    print("-" * 60)
    
    results = run_scraper(url, output_file)
    
    sys.exit(0 if results['success'] else 1)


if __name__ == '__main__':
    main()
