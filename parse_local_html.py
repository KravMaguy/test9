#!/usr/bin/env python3
"""
PropPublica PPP Loan Parser
---------------------------
Parses locally saved HTML files from PropPublica's PPP Loan database.
Use this when the website blocks direct scraping.

Usage:
    python parse_local_html.py <html_file>
    python parse_local_html.py pagecontent.html

Output:
    Creates a JSON file named 'loans_<timestamp>.json'
"""

import sys
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from scrapy.selector import Selector


def parse_loan_html(html_content: str) -> Dict[str, Any]:
    """
    Parse PPP loan data from HTML content.
    
    Args:
        html_content: Raw HTML string
    
    Returns:
        Dictionary containing parsed loans and metadata
    """
    
    selector = Selector(text=html_content)
    
    # Extract search info
    search_query = selector.css('input[name="q"]::attr(value)').get('')
    result_header = selector.css('h1::text').get('')
    
    loans = []
    errors = []
    
    # Find all loan entries - they are in <li> elements
    loan_items = selector.css('li.list.pt3')
    
    print(f"Found {len(loan_items)} loan entries")
    
    if not loan_items:
        # Try alternative selectors
        loan_items = selector.css('ul li.list')
        print(f"Alternative selector found {len(loan_items)} entries")
    
    for idx, item in enumerate(loan_items):
        try:
            loan_data = extract_loan_data(item, idx)
            if loan_data and loan_data.get('recipient'):
                loans.append(loan_data)
        except Exception as e:
            errors.append({
                'error_type': 'ExtractionError',
                'message': f'Failed to extract loan {idx}: {str(e)}',
                'timestamp': datetime.now().isoformat(),
            })
    
    return {
        'search_query': search_query,
        'result_header': result_header.strip() if result_header else '',
        'total_loans': len(loans),
        'loans': loans,
        'errors': errors,
        'parsed_at': datetime.now().isoformat(),
    }


def extract_loan_data(item, index: int) -> Dict[str, Any]:
    """Extract loan data from a single list item."""
    
    # Recipient name and URL
    recipient_link = item.css('div.tiempos-text.lh-title a')
    recipient_name = recipient_link.css('::text').get('').strip()
    recipient_url = recipient_link.css('::attr(href)').get('')
    if recipient_url and not recipient_url.startswith('http'):
        recipient_url = f"https://projects.propublica.org{recipient_url}"
    
    # Initialize values
    location = ''
    loan_status = ''
    loan_amount = ''
    date_approved = ''
    
    # Find the flex container with the details
    flex_container = item.css('div.flex.flex-wrap')
    
    if flex_container:
        # Each detail block is in a div with width classes
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
    
    # Alternative extraction if the above didn't work
    if not location or not loan_amount:
        all_values = item.css('div.f5.tiempos-text::text').getall()
        all_values = [v.strip() for v in all_values if v.strip()]
        
        for val in all_values:
            if not location and ',' in val and len(val.split(',')) == 2:
                parts = val.split(',')
                if len(parts[1].strip()) == 2:  # State abbreviation
                    location = val
            elif not loan_amount and val.startswith('$'):
                loan_amount = val
            elif not loan_status and any(keyword in val for keyword in 
                ['Forgiven', 'Active', 'Paid', 'Exempt', 'Cancelled']):
                loan_status = val
            elif not date_approved and any(month in val for month in 
                ['Jan', 'Feb', 'March', 'April', 'May', 'June', 
                 'July', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec']):
                date_approved = val
    
    loan_data = {
        'index': index + 1,
        'recipient': recipient_name,
        'detail_url': recipient_url,
        'location': location,
        'loan_status': loan_status,
        'loan_amount': loan_amount,
        'loan_amount_numeric': parse_amount(loan_amount),
        'date_approved': date_approved,
    }
    
    return loan_data


def parse_amount(amount_str: str) -> Optional[float]:
    """Parse loan amount string to numeric value."""
    if not amount_str:
        return None
    try:
        cleaned = re.sub(r'[$,\s]', '', amount_str)
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def main():
    """Main entry point."""
    
    print("""
╔═══════════════════════════════════════════════════════════╗
║          PropPublica PPP Loan HTML Parser                 ║
╠═══════════════════════════════════════════════════════════╣
║  Parses locally saved HTML files from PropPublica's       ║
║  coronavirus bailout database.                            ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    if len(sys.argv) < 2:
        # Default to pagecontent.html
        html_file = "focus_scraper/pagecontent.html"
        print(f"No HTML file provided, using default: {html_file}")
    else:
        html_file = sys.argv[1]
    
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Validate file exists
    html_path = Path(html_file)
    if not html_path.exists():
        print(f"ERROR: File not found: {html_file}")
        sys.exit(1)
    
    print(f"Parsing: {html_file}")
    print("-" * 60)
    
    # Read HTML content
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"ERROR: Failed to read file: {str(e)}")
        sys.exit(1)
    
    # Parse the HTML
    results = parse_loan_html(html_content)
    
    # Generate output filename
    if not output_file:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'loans_{timestamp}.json'
    
    # Save results
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*60}")
        print("PARSING COMPLETE")
        print(f"{'='*60}")
        print(f"Output saved to: {output_file}")
        print(f"Search query: {results['search_query']}")
        print(f"Total loans found: {results['total_loans']}")
        print(f"Errors: {len(results['errors'])}")
        
        if results['loans']:
            print(f"\n{'='*60}")
            print("LOAN DATA:")
            print(f"{'='*60}")
            for loan in results['loans']:
                print(f"\n{loan['index']}. {loan['recipient']}")
                print(f"   Location: {loan['location']}")
                print(f"   Amount: {loan['loan_amount']}")
                print(f"   Status: {loan['loan_status']}")
                print(f"   Date Approved: {loan['date_approved']}")
                print(f"   URL: {loan['detail_url']}")
        
        print(f"\n{'='*60}\n")
        
    except IOError as e:
        print(f"\nFailed to write output file: {str(e)}")
        sys.exit(1)
    
    return results


if __name__ == '__main__':
    main()
