#!/usr/bin/env python3
"""
Briefly — publish pipeline (stub)
Reads APPROVED articles from SQLite and would push to Supabase + trigger Expo notifications.
Replace the stubs below with real Supabase and Expo calls when ready.
"""

import os
from dotenv import load_dotenv

from db import get_conn, get_articles_by_status, update_status

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
EXPO_PUSH_TOKEN = os.getenv("EXPO_PUSH_TOKEN", "")


def push_to_supabase(article: dict) -> bool:
    """Upload article + card to Supabase. Stub — implement when Supabase is configured."""
    print(f"  [stub] would upload to Supabase: {article['headline'][:60]}")
    return False


def send_expo_notification(headline: str, summary: str) -> bool:
    """Send Expo push notification. Stub — implement with real push token."""
    print(f"  [stub] would send push: {headline[:60]}")
    return False


def main():
    conn = get_conn()
    approved = get_articles_by_status(conn, "APPROVED")
    print(f"Found {len(approved)} APPROVED articles")

    for row in approved:
        article = dict(row)
        print(f"\nPublishing: {article['headline'][:70]}")
        ok = push_to_supabase(article)
        if ok:
            send_expo_notification(article["headline"], article["summary"])
            update_status(conn, article["id"], "PUBLISHED")
            print("  done")
        else:
            print("  skipped (stub not implemented)")

    conn.close()


if __name__ == "__main__":
    main()
