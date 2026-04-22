#!/usr/bin/env python3
"""
LLM quality test loop — reads articles from Google Sheet, runs LLM, writes results back.
No cards generated. No DB writes. Purely for testing llm.py output.

Usage:
  python test_llm.py              # process all rows with blank summary
  python test_llm.py --limit 5    # process at most 5 rows
  python test_llm.py --reset      # clear ALL output columns first, then process

Workflow:
  1. Run export_to_sheets.py once to load articles into the sheet
  2. Run this script to fill in LLM output columns
  3. Review results in Google Sheet
  4. Delete the 'summary' cell on any row to re-run it
  5. Re-run this script

Output columns written: llm_headline, categories, tags, summary,
                        word_count, qa_pass, review_score, review_verdict, review_issues

Model switching examples:
  python test_llm.py --model llama3.2:3b
  python test_llm.py --model qwen2.5:14b --host http://localhost:11434
  python test_llm.py --model llama3:8b --host https://api.ollama.ai --api-key YOUR_KEY
  python test_llm.py --list-models
"""

import argparse
import json
import os
import pickle
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# ── Parse model/host/key args BEFORE importing llm so env vars are set first ──
_pre_parser = argparse.ArgumentParser(add_help=False)
_pre_parser.add_argument("--model", default="")
_pre_parser.add_argument("--host", default="")
_pre_parser.add_argument("--api-key", default="")
_pre_args, _ = _pre_parser.parse_known_args()

load_dotenv()

if _pre_args.model:
    os.environ["OLLAMA_MODEL"] = _pre_args.model
if _pre_args.host:
    os.environ["OLLAMA_HOST"] = _pre_args.host
if _pre_args.api_key:
    os.environ["OLLAMA_API_KEY"] = _pre_args.api_key

import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

import llm

load_dotenv()

SHEET_ID = os.getenv("SHEET_ID", "")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"
TOKEN_FILE = Path(__file__).parent / "token.pickle"

# Must match export_to_sheets.py ALL_COLUMNS order
COLUMNS = [
    "id", "source", "url", "headline", "scraped_content",
    "llm_headline", "categories", "tags",
    "summary", "word_count", "qa_pass",
    "review_score", "review_verdict", "review_issues",
]
COL = {name: idx for idx, name in enumerate(COLUMNS)}  # name → 0-based index


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
                    "credentials.json not found. See setup instructions in export_to_sheets.py"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return gspread.authorize(creds)


def col_letter(zero_idx: int) -> str:
    """Convert 0-based column index to sheet letter (0→A, 25→Z, 26→AA)."""
    result = ""
    n = zero_idx + 1
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def write_result(sheet, row_idx: int, result: dict):
    """Write LLM output columns for a single row. row_idx is 1-based (sheet row)."""
    updates = {
        "llm_headline":   result.get("headline", ""),
        "categories":     ", ".join(result.get("categories") or []),
        "tags":           ", ".join(result.get("tags") or []),
        "summary":        result.get("summary", ""),
        "word_count":     str(result.get("word_count", "")),
        "qa_pass":        str(result.get("qa_pass", "")),
        "review_score":   str(result.get("review_score", "")),
        "review_verdict": result.get("review_verdict", ""),
        "review_issues":  "; ".join(result.get("review_issues") or []),
    }
    for col_name, value in updates.items():
        col_idx = COL[col_name]
        cell = f"{col_letter(col_idx)}{row_idx}"
        sheet.update_acell(cell, value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit",       type=int, default=0,  help="Max rows to process (0 = all)")
    parser.add_argument("--reset",       action="store_true",  help="Clear all output columns first")
    parser.add_argument("--model",       default="",           help="Override Ollama model name")
    parser.add_argument("--host",        default="",           help="Override Ollama host URL")
    parser.add_argument("--api-key",     default="",           help="API key for Ollama cloud")
    parser.add_argument("--list-models", action="store_true",  help="List available models and exit")
    args = parser.parse_args()

    if args.list_models:
        import requests as _req
        try:
            resp = _req.get(f"{llm.OLLAMA_HOST}/api/tags", timeout=5)
            models = [m["name"] for m in resp.json().get("models", [])]
            print(f"Available models on {llm.OLLAMA_HOST}:")
            for m in models:
                marker = " ◀ current" if m == llm.MODEL or m.split(":")[0] == llm.MODEL.split(":")[0] else ""
                print(f"  {m}{marker}")
        except Exception as e:
            print(f"Could not reach {llm.OLLAMA_HOST}: {e}")
        sys.exit(0)

    if not SHEET_ID:
        print("ERROR: SHEET_ID not set in .env")
        sys.exit(1)

    print("Checking Ollama …")
    if not llm.is_ollama_running():
        print(f"ERROR: Ollama not reachable at {llm.OLLAMA_HOST}")
        print(f"  Start Ollama and pull the model:  ollama pull {llm.MODEL}")
        sys.exit(1)
    print(f"  Ollama OK — model: {llm.MODEL}")

    print("Connecting to Google Sheets …")
    client = get_client()
    sheet = client.open_by_key(SHEET_ID).sheet1

    all_rows = sheet.get_all_values()
    if not all_rows:
        print("Sheet is empty. Run export_to_sheets.py first.")
        sys.exit(1)

    header = all_rows[0]
    data_rows = all_rows[1:]  # skip header

    if args.reset:
        print("Resetting output columns …")
        output_cols = ["llm_headline", "categories", "tags", "summary",
                       "word_count", "qa_pass", "review_score", "review_verdict", "review_issues"]
        for col_name in output_cols:
            if col_name in header:
                col_idx = header.index(col_name)
                col_let = col_letter(col_idx)
                # Clear the entire output column (skip header row)
                if len(data_rows) > 0:
                    sheet.batch_clear([f"{col_let}2:{col_let}{len(data_rows) + 1}"])
        all_rows = sheet.get_all_values()
        data_rows = all_rows[1:]
        print("  Reset done.")

    # Find rows with blank summary
    try:
        summary_col = header.index("summary")
        headline_col = header.index("headline")
        content_col = header.index("scraped_content")
    except ValueError as e:
        print(f"ERROR: column not found in sheet: {e}")
        print("Re-run export_to_sheets.py to refresh the sheet structure.")
        sys.exit(1)

    pending = [
        (i + 2, row)  # i+2 = 1-based sheet row (row 1 is header)
        for i, row in enumerate(data_rows)
        if not (row[summary_col] if summary_col < len(row) else "").strip()
        and (row[content_col] if content_col < len(row) else "").strip()
    ]

    if not pending:
        print("No rows with blank summary found. Delete a summary cell to re-test that row.")
        sys.exit(0)

    if args.limit:
        pending = pending[:args.limit]

    print(f"Found {len(pending)} rows to process\n")

    processed = 0
    skipped = 0

    for sheet_row, row in pending:
        headline = row[headline_col] if headline_col < len(row) else ""
        content = row[content_col] if content_col < len(row) else ""

        print(f"[{processed + 1}/{len(pending)}] {headline[:70]}")

        result = llm.process_article(headline, content)

        if result is None:
            print("  ✗ LLM failed — skipping\n")
            skipped += 1
            continue

        if not result.get("qa_pass"):
            print(f"  ✗ qa_pass=False — writing result anyway for review\n")

        write_result(sheet, sheet_row, result)

        wc = result.get("word_count", "?")
        score = result.get("review_score", "?")
        verdict = result.get("review_verdict", "")
        qa = result.get("qa_pass", False)
        print(f"  ✓ words={wc}  score={score}/50  verdict={verdict}  qa={'PASS' if qa else 'FAIL'}\n")

        processed += 1
        time.sleep(0.5)  # avoid hammering Ollama

    print(f"Done. Processed: {processed}  Skipped: {skipped}")
    print(f"  View results: https://docs.google.com/spreadsheets/d/{SHEET_ID}")


if __name__ == "__main__":
    main()
