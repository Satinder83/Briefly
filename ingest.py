#!/usr/bin/env python3
"""
Briefly — ingest pipeline
Fetch RSS feeds → scrape articles → LLM tag+summarize → generate cards → store in SQLite
"""

import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import feedparser
import requests
import trafilatura
from dotenv import load_dotenv

import card_gen
import llm
from db import get_conn, get_existing_urls, init_db, insert_article

load_dotenv()

MAX_PER_FEED = int(os.getenv("MAX_PER_FEED", "5"))
SCRAPE_TIMEOUT = int(os.getenv("SCRAPE_TIMEOUT", "8"))
MIN_CONTENT_LEN = 200

FEEDS = [
    ("CBC News",       "https://rss.cbc.ca/lineup/topstories.xml"),
    ("CTV News",       "https://www.ctvnews.ca/rss/ctvnews-ca-top-stories-public-rss-1.822009"),
    ("Global News",    "https://globalnews.ca/feed/"),
    ("CP24",           "https://www.cp24.com/rss/cp24"),
    ("Financial Post", "https://financialpost.com/feed/"),
    ("BNN Bloomberg",  "https://www.bnnbloomberg.ca/arc/outboundfeeds/rss/"),
    ("Reuters",        "https://feeds.reuters.com/reuters/topNews"),
    ("AP News",        "https://rsshub.app/apnews/topics/apf-topnews"),
    ("TechCrunch",     "https://techcrunch.com/feed/"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Briefly/1.0"}


def safe_scrape(url: str) -> str:
    try:
        resp = requests.get(url, timeout=SCRAPE_TIMEOUT, headers=HEADERS)
        content = trafilatura.extract(resp.text) or ""
        return content[:5000]
    except requests.exceptions.Timeout:
        return ""
    except Exception as e:
        print(f"    [scrape] error: {e}")
        return ""


def extract_image_from_entry(entry) -> str | None:
    """Try media_content → media_thumbnail → enclosures → og:image."""
    # feedparser normalises media: fields
    for attr in ("media_content", "media_thumbnail"):
        items = getattr(entry, attr, [])
        if items and isinstance(items, list):
            url = items[0].get("url", "")
            if url:
                return url

    for enc in getattr(entry, "enclosures", []):
        if enc.get("type", "").startswith("image/"):
            return enc.get("href") or enc.get("url")

    return None


def extract_og_image(url: str) -> str | None:
    try:
        resp = requests.get(url, timeout=6, headers=HEADERS)
        # simple regex — avoids adding BeautifulSoup dependency
        match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            resp.text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
        match = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            resp.text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def process_feed(source_name: str, feed_url: str, existing_urls: set, conn) -> int:
    print(f"\n[{source_name}] fetching feed …")
    try:
        resp = requests.get(feed_url, timeout=10, headers=HEADERS)
        feed = feedparser.parse(resp.text)
    except requests.exceptions.Timeout:
        print(f"  feed timed out, skipping")
        return 0
    except Exception as e:
        print(f"  feed error: {e}")
        return 0

    print(f"  {len(feed.entries)} entries")
    added = 0

    for entry in feed.entries:
        if added >= MAX_PER_FEED:
            break

        url = entry.get("link", "").strip()
        headline = entry.get("title", "").strip()
        if not url or not headline:
            continue
        if url in existing_urls:
            print(f"  skip (dup): {headline[:70]}")
            continue

        print(f"  scraping: {url[:80]}")
        content = safe_scrape(url)
        if len(content) < MIN_CONTENT_LEN:
            print(f"  skip (content too short: {len(content)} chars)")
            existing_urls.add(url)
            continue

        print(f"  {len(content)} chars — calling LLM …")
        result = llm.process_article(headline, content)
        if result is None:
            print("  skip (LLM failed)")
            continue
        if not result.get("qa_pass", False):
            print(f"  skip (qa_pass=False)")
            existing_urls.add(url)
            continue

        category = result["category"]
        summary = result["summary"]
        word_count = result.get("word_count", 0)

        image_url = extract_image_from_entry(entry) or extract_og_image(url)

        import uuid
        article_id = str(uuid.uuid4())
        print(f"  generating card …")
        card_path = card_gen.generate_card(
            article_id=article_id,
            headline=headline,
            summary=summary,
            category=category,
            source=source_name,
            image_url=image_url,
        )

        insert_article(conn, {
            "id": article_id,
            "source": source_name,
            "headline": headline,
            "url": url,
            "scraped_content": content,
            "category": category,
            "summary": summary,
            "word_count": word_count,
            "article_image_url": image_url or "",
            "card_path": card_path,
            "status": "PENDING",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "published_at": None,
        })
        existing_urls.add(url)
        added += 1
        print(f"  ✓ {headline[:70]}")
        time.sleep(0.5)

    return added


def main():
    print("Briefly ingest — starting")

    if not llm.is_ollama_running():
        print(
            f"ERROR: Ollama not reachable at {llm.OLLAMA_HOST}\n"
            "Start Ollama and ensure the model is pulled:\n"
            f"  ollama pull {llm.MODEL}"
        )
        sys.exit(1)

    init_db()
    conn = get_conn()
    existing_urls = get_existing_urls(conn)
    print(f"  existing articles in DB: {len(existing_urls)}")

    total = 0
    for source_name, feed_url in FEEDS:
        try:
            total += process_feed(source_name, feed_url, existing_urls, conn)
        except Exception as e:
            print(f"  [{source_name}] unexpected error: {e}")

    conn.close()
    print(f"\nDone. Total added: {total}")


if __name__ == "__main__":
    main()
