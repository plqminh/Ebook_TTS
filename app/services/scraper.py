import requests
from bs4 import BeautifulSoup
from typing import Optional

class WebScraper:
    """
    Service to scrape and clean text from URLs (Read Mode).
    """

    @staticmethod
    def fetch_content(url: str) -> dict:
        """
        Fetches the URL and attempts to extract the main content.
        Returns a dict with 'title' and 'content'.
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove unwanted elements
            for tag in soup(['script', 'style', 'nav', 'footer', 'iframe', 'ads']):
                tag.decompose()
            
            # Simple heuristic for title
            title = soup.title.string if soup.title else url
            
            # Simple heuristic for main content: look for <article> or largest <div>
            # This is basic; libraries like 'trafilatura' are better for this in production.
            article = soup.find('article')
            if article:
                text = article.get_text(separator='\n\n')
            else:
                # Fallback: get all p tags
                paragraphs = soup.find_all('p')
                text = "\n\n".join([p.get_text() for p in paragraphs if len(p.get_text()) > 50])
            
            return {
                "title": title.strip(),
                "content": text.strip()
            }
        except Exception as e:
            return {
                "title": "Error",
                "content": f"Failed to fetch {url}: {str(e)}"
            }
