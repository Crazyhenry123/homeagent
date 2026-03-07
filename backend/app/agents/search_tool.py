"""Web search tool — allows the agent to look up current information."""

import logging

import requests
from strands import tool

logger = logging.getLogger(__name__)


@tool(
    name="web_search",
    description=(
        "Search the web for current information. Use this when you need "
        "up-to-date facts, news, weather, events, or any information that "
        "may have changed since your training data. Returns titles, snippets, "
        "and URLs from search results."
    ),
)
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (1-10, default 5).
    """
    max_results = max(1, min(10, max_results))

    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; HomeAgent/1.0; "
                    "+https://github.com/homeagent)"
                )
            },
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException:
        logger.exception("Web search request failed for query: %s", query)
        return "Web search is temporarily unavailable. Please try again later."

    # Parse results from DuckDuckGo HTML response
    results = _parse_ddg_html(resp.text, max_results)

    if not results:
        return f"No results found for: {query}"

    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        if r.get("url"):
            lines.append(f"   URL: {r['url']}")
        lines.append("")

    return "\n".join(lines)


def _parse_ddg_html(html: str, max_results: int) -> list[dict]:
    """Parse DuckDuckGo HTML search results."""
    results = []

    try:
        from html.parser import HTMLParser

        class DDGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_title = False
                self.in_snippet = False
                self.current: dict = {}
                self.results: list[dict] = []

            def handle_starttag(self, tag: str, attrs: list) -> None:
                attr_dict = dict(attrs)
                classes = attr_dict.get("class", "")

                if tag == "a" and "result__a" in classes:
                    self.in_title = True
                    self.current = {
                        "title": "",
                        "url": attr_dict.get("href", ""),
                        "snippet": "",
                    }
                elif tag == "a" and "result__snippet" in classes:
                    self.in_snippet = True

            def handle_endtag(self, tag: str) -> None:
                if tag == "a" and self.in_title:
                    self.in_title = False
                elif tag == "a" and self.in_snippet:
                    self.in_snippet = False
                    if self.current.get("title"):
                        self.results.append(self.current)
                    self.current = {}

            def handle_data(self, data: str) -> None:
                if self.in_title:
                    self.current["title"] += data.strip()
                elif self.in_snippet:
                    self.current["snippet"] += data.strip()

        parser = DDGParser()
        parser.feed(html)
        results = parser.results[:max_results]
    except Exception:
        logger.exception("Failed to parse DuckDuckGo results")

    return results
