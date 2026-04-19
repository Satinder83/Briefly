#!/usr/bin/env python3
"""
Briefly — local review dashboard
Run: uvicorn review.main:app --reload
Open: http://localhost:8000
"""

import json
import sys
from pathlib import Path

# allow importing db, etc. from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import jinja2
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import get_all_articles, get_articles_by_status, get_conn, init_db, update_status, update_summary

app = FastAPI(title="Briefly Review")

TEMPLATES_DIR = Path(__file__).parent / "templates"
CARDS_DIR = Path(__file__).parent.parent / "output" / "cards"


def _fromjson(value):
    if not value:
        return []
    try:
        return json.loads(value)
    except Exception:
        return [value]


_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
    cache_size=0,
)
_jinja_env.filters["fromjson"] = _fromjson
templates = Jinja2Templates(env=_jinja_env)

# serve card images at /cards/<filename>
if CARDS_DIR.exists():
    app.mount("/cards", StaticFiles(directory=str(CARDS_DIR)), name="cards")


@app.on_event("startup")
def startup():
    init_db()


def _get_conn():
    return get_conn()


@app.get("/", response_class=HTMLResponse)
def index(request: Request, status: str = "PENDING"):
    conn = _get_conn()
    if status == "ALL":
        articles = get_all_articles(conn)
    else:
        articles = get_articles_by_status(conn, status)
    conn.close()
    counts = _get_counts()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"articles": articles, "current_status": status, "counts": counts},
    )


def _get_counts() -> dict:
    conn = _get_conn()
    result = {}
    for s in ("PENDING", "APPROVED", "REJECTED", "ALL"):
        if s == "ALL":
            row = conn.execute("SELECT COUNT(*) as n FROM articles").fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) as n FROM articles WHERE status = ?", (s,)
            ).fetchone()
        result[s] = row["n"]
    conn.close()
    return result


@app.post("/approve-all")
def approve_all():
    conn = _get_conn()
    conn.execute("UPDATE articles SET status='APPROVED' WHERE status='PENDING'")
    conn.commit()
    conn.close()
    return RedirectResponse("/", status_code=303)


@app.post("/reject-all")
def reject_all():
    conn = _get_conn()
    conn.execute("UPDATE articles SET status='REJECTED' WHERE status='PENDING'")
    conn.commit()
    conn.close()
    return RedirectResponse("/", status_code=303)


@app.post("/approve/{article_id}")
def approve(article_id: str):
    conn = _get_conn()
    update_status(conn, article_id, "APPROVED")
    conn.close()
    return RedirectResponse("/", status_code=303)


@app.post("/reject/{article_id}")
def reject(article_id: str):
    conn = _get_conn()
    update_status(conn, article_id, "REJECTED")
    conn.close()
    return RedirectResponse("/", status_code=303)


@app.post("/edit/{article_id}")
def edit(article_id: str, summary: str = Form(...)):
    conn = _get_conn()
    update_summary(conn, article_id, summary.strip())
    conn.close()
    return RedirectResponse("/", status_code=303)
