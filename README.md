# test9

scrape weburl:
https://projects.propublica.org/coronavirus/bailouts/search?q=90210+medical&v=1


Static Scrape Step 1: completed
Workaround for Scraping Live Data:
Since the site blocks direct scraping, next options:

Save HTML from browser, then parse with parse_local_html.py
Use Playwright/Selenium to automate a real browser
Use a proxy service that handles anti-bot measures

Setup 
The site blocks direct scraping (403 Forbidden) - they detect bots
The data IS in the HTML - it's server-side rendered, not JavaScript-loaded
You saved the HTML manually from Chrome, which bypasses the blocking



Step 2:
Match a buisness to an owner
 ADVANCED HAIR MEDICAL, P.C.
   Location: BEVERLY HILLS, CA
   