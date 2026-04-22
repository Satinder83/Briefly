#!/usr/bin/env python3
"""
Export briefly.db articles to a Google Sheet for LLM testing.

FIRST-TIME SETUP (do this once):
──────────────────────────────────────────────────────────────────
1. Go to https://console.cloud.google.com
2. Click "Select a project" → "New Project" → name it "Briefly" → Create
3. In the search bar type "Google Sheets API" → click it → Enable
4. Go to "APIs & Services" → "Credentials"
5. Click "Create Credentials" → "OAuth client ID"
6. If prompted, configure the consent screen first:
   - User type: External → Create
   - App name: Briefly, your email as support email → Save
   - Back to Credentials → Create Credentials → OAuth client ID
7. Application type: Desktop app → Name: Briefly → Create
8. Click "Download JSON" → save as credentials.json in this project folder
9. pip install gspread google-auth-oauthlib

Then create a Google Sheet:
10. Go to sheets.google.com → create a blank sheet → name it "Briefly LLM Test"
11. Copy the sheet ID from the URL:
    https://docs.google.com/spreadsheets/d/  THIS_PART_HERE  /edit
12. Add to your .env:  SHEET_ID=paste-your-sheet-id-here
──────────────────────────────────────────────────────────────────

Run:  python export_to_sheets.py
"""

import os
import json
import pickle
from pathlib import Path

from dotenv import load_dotenv
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from db import get_conn, get_all_articles, init_db

load_dotenv()

SHEET_ID = os.getenv("SHEET_ID", "")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"
TOKEN_FILE = Path(__file__).parent / "token.pickle"

# Columns exported to the sheet
EXPORT_COLUMNS = [
    "id", "source", "url", "headline", "scraped_content",
]

# Output columns — written by test_llm.py, left blank here
OUTPUT_COLUMNS = [
    "llm_headline", "categories", "tags",
    "summary", "word_count", "qa_pass",
    "review_score", "review_verdict", "review_issues",
]

ALL_COLUMNS = EXPORT_COLUMNS + OUTPUT_COLUMNS


def get_client() -> gspread.Client:
    creds = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    "credentials.json not found. Follow the setup instructions at the top of this file."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            # Opens browser for one-time login
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return gspread.authorize(creds)


def main():
    if not SHEET_ID:
        print("ERROR: SHEET_ID not set in .env")
        print("Create a Google Sheet, copy its ID from the URL, add SHEET_ID=... to .env")
        return

    print("Connecting to Google Sheets …")
    client = get_client()
    sheet = client.open_by_key(SHEET_ID).sheet1

    print("Reading articles from briefly.db …")
    init_db()
    conn = get_conn()
    articles = get_all_articles(conn)
    conn.close()

    if not articles:
        print("No articles found in DB.")
        return

    print(f"Found {len(articles)} articles")

    # Build rows
    rows = [ALL_COLUMNS]  # header row
    for a in articles:
        row = [str(a.get(col, "") or "") for col in EXPORT_COLUMNS]
        row += [""] * len(OUTPUT_COLUMNS)  # blank output columns
        rows.append(row)

    # Clear sheet and write
    sheet.clear()
    sheet.update(rows, "A1")

    # Bold the header row
    sheet.format("A1:R1", {"textFormat": {"bold": True}})

    print(f"✓ Exported {len(articles)} articles to Google Sheet")
    print(f"  Open: https://docs.google.com/spreadsheets/d/{SHEET_ID}")
    print()
    print("Next steps:")
    print("  - In the sheet, clear the 'summary' column for rows you want to test")
    print("  - Run: python test_llm.py")


if __name__ == "__main__":
    main()
