import os
import re
import xml.etree.ElementTree as ET
from collections import Counter

import httpx


FACT_CHECK_ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
NEWS_SEARCH_ENDPOINT = "https://news.google.com/rss/search"
STOP_WORDS = {
    "about", "after", "again", "against", "also", "among", "and", "are",
    "been", "before", "being", "between", "both", "can", "could", "does",
    "during", "each", "for", "from", "has", "have", "having", "here", "into",
    "itself", "more", "most", "not", "other", "our", "over", "same", "she",
    "some", "such", "than", "that", "the", "their", "them", "then", "there",
    "these", "they", "this", "through", "under", "very", "was", "were", "what",
    "when", "where", "which", "while", "who", "why", "with", "would", "you",
    "your",
}
VERDICT_LABELS = {
    "supported": "Supported by available evidence",
    "contradicted": "Contradicted by available evidence",
    "mixed": "Mixed evidence",
    "inconclusive": "Inconclusive",
}


def keywords_for(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]{2,}", text.lower())
    counts = Counter(word for word in words if word not in STOP_WORDS)
    return [word for word, _ in counts.most_common(6)]


def _rating_category(rating: str) -> str:
    normalized = re.sub(r"[^a-z0-9 ]", " ", rating.lower())
    normalized = " ".join(normalized.split())
    contradicted = (
        "false", "pants on fire", "mostly false", "four pinocchios",
        "three pinocchios", "two pinocchios", "incorrect", "not true",
        "misleading", "debunked",
    )
    supported = (
        "true", "mostly true", "correct", "accurate", "accurate but",
        "four stars", "three stars",
    )
    if any(term in normalized for term in contradicted):
        return "contradicted"
    if any(term in normalized for term in supported):
        return "supported"
    return "inconclusive"


def _verdict(sources: list[dict]) -> str:
    categories = {_rating_category(source["rating"]) for source in sources}
    categories.discard("inconclusive")
    if categories == {"supported"}:
        return "supported"
    if categories == {"contradicted"}:
        return "contradicted"
    if len(categories) > 1:
        return "mixed"
    return "inconclusive"


def _search_news(claim: str) -> list[dict]:
    try:
        response = httpx.get(
            NEWS_SEARCH_ENDPOINT,
            params={"q": claim[:500], "hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
            headers={"User-Agent": "TruthLens/1.0 (student fact-checking project)"},
            timeout=12,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except (httpx.HTTPError, ET.ParseError) as exc:
        raise RuntimeError(
            "Free news search is temporarily unavailable. Please try again in a moment."
        ) from exc

    sources = []
    for item in root.findall("./channel/item")[:10]:
        link = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        if not link or not title:
            continue
        publisher_node = item.find("source")
        publisher = (publisher_node.text or "").strip() if publisher_node is not None else ""
        sources.append(
            {
                "title": title,
                "publisher": publisher or "Google News search result",
                "url": link,
                "rating": "News result — not a fact-check",
                "review_date": (item.findtext("pubDate") or "").strip() or None,
                "source_type": "news",
            }
        )
    return sources


def analyze_claim(claim: str) -> dict:
    keywords = keywords_for(claim)
    api_key = os.getenv("GOOGLE_FACT_CHECK_API_KEY", "").strip()
    if not api_key:
        sources = _search_news(claim)
        return {
            "verdict": "inconclusive",
            "summary": (
                f"The free news search returned {len(sources)} article"
                f"{'s' if len(sources) != 1 else ''} related to this query. News coverage is "
                "context, not fact-checking or proof; no truth rating was assigned. Add a "
                "Google Fact Check Tools API key to search published fact-check reviews."
            ),
            "mode": "news_search",
            "sources": sources,
            "keywords": keywords,
        }

    try:
        response = httpx.get(
            FACT_CHECK_ENDPOINT,
            params={"query": claim[:1000], "key": api_key, "pageSize": 10},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("Fact-check search is temporarily unavailable. Please try again.") from exc

    sources = []
    for result in payload.get("claims", []):
        claim_review = result.get("claimReview") or []
        for review in claim_review:
            url = review.get("url")
            rating = (review.get("textualRating") or "").strip()
            if not url or not rating:
                continue
            sources.append(
                {
                    "title": (result.get("text") or claim).strip(),
                    "publisher": (review.get("publisher") or {}).get("name") or "Fact-check publisher",
                    "url": url,
                    "rating": rating,
                    "review_date": review.get("reviewDate"),
                    "source_type": "fact_check",
                }
            )

    verdict = _verdict(sources) if sources else "inconclusive"
    if sources:
        summary = (
            f"The Fact Check Tools API returned {len(sources)} published review"
            f"{'s' if len(sources) != 1 else ''}. The result reflects those reviewers' "
            "reported ratings, not an independent verification by Truth Lens. Read each "
            "review for its evidence, date, and context."
        )
    else:
        summary = (
            "No published fact-check reviews were returned for this query. That is not "
            "evidence that the claim is true or false; the result remains inconclusive."
        )
    return {
        "verdict": verdict,
        "summary": summary,
        "mode": "live",
        "sources": sources,
        "keywords": keywords,
    }
