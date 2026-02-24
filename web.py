"""
skills/web.py — Web browsing and search skill for MAX.

Capabilities:
- Search the web via DuckDuckGo (no API key required)
- Fetch and extract clean text from URLs
- Summarize web pages
"""

import asyncio
import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from skills.base import BaseSkill, skill_action

logger = logging.getLogger("MAX.skills.web")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class WebSkill(BaseSkill):
    name = "web"
    description = "Search the web and browse URLs"

    def __init__(self, settings=None):
        super().__init__(settings)
        self._client = httpx.AsyncClient(
            headers=HEADERS,
            timeout=15.0,
            follow_redirects=True,
        )

    @skill_action(description="Search the web for a query and return top results")
    async def search(self, query: str, max_results: int = 5) -> str:
        """DuckDuckGo search — no API key needed."""
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }

        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            results = []

            # Abstract (instant answer)
            if data.get("AbstractText"):
                results.append(f"**Quick answer:** {data['AbstractText']}")
                if data.get("AbstractURL"):
                    results.append(f"Source: {data['AbstractURL']}")

            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    text = topic["Text"][:200]
                    url_val = topic.get("FirstURL", "")
                    results.append(f"• {text}\n  {url_val}")

            if not results:
                return f"No results found for: {query}"

            return f"Search results for '{query}':\n\n" + "\n\n".join(results)

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return f"Search failed: {str(e)}"

    @skill_action(description="Fetch the content of a URL and return clean readable text")
    async def fetch_url(self, url: str, max_chars: int = 3000) -> str:
        """Fetch a URL and extract readable text content."""
        try:
            response = await self._client.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove boilerplate elements
            for tag in soup(["script", "style", "nav", "footer", "header",
                              "aside", "advertisement", "iframe", "noscript"]):
                tag.decompose()

            # Extract main content
            main = (
                soup.find("article") or
                soup.find("main") or
                soup.find(id="content") or
                soup.find(class_="content") or
                soup.body
            )

            if main:
                text = main.get_text(separator="\n", strip=True)
            else:
                text = soup.get_text(separator="\n", strip=True)

            # Clean up whitespace
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = text[:max_chars]

            if len(response.text) > max_chars:
                text += f"\n\n[Content truncated. Full page: {url}]"

            return f"Content from {url}:\n\n{text}"

        except httpx.HTTPStatusError as e:
            return f"HTTP error {e.response.status_code} fetching {url}"
        except Exception as e:
            logger.error(f"Fetch failed for {url}: {e}")
            return f"Failed to fetch {url}: {str(e)}"

    @skill_action(description="Get the title and meta description of a URL without downloading full content")
    async def peek_url(self, url: str) -> str:
        """Quick peek at a URL — just title and description."""
        try:
            response = await self._client.head(url)
            # Some servers don't support HEAD — fall back to GET with short read
            if response.status_code == 405:
                response = await self._client.get(url)

            response = await self._client.get(url)
            soup = BeautifulSoup(response.text[:10000], "html.parser")

            title = soup.find("title")
            description = (
                soup.find("meta", attrs={"name": "description"}) or
                soup.find("meta", attrs={"property": "og:description"})
            )

            title_text = title.get_text(strip=True) if title else "No title"
            desc_text = description.get("content", "No description") if description else "No description"

            return f"URL: {url}\nTitle: {title_text}\nDescription: {desc_text}"

        except Exception as e:
            return f"Could not peek at {url}: {str(e)}"

    async def close(self):
        await self._client.aclose()
