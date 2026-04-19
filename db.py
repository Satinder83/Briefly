import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "briefly.db"


def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_conn(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = _dict_factory
    return conn


def init_db(db_path=DB_PATH):
    conn = get_conn(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id                TEXT PRIMARY KEY,
            source            TEXT,
            headline          TEXT,
            url               TEXT UNIQUE,
            scraped_content   TEXT,
            category          TEXT,
            categories        TEXT,
            tags              TEXT,
            summary           TEXT,
            word_count        INTEGER,
            article_image_url TEXT,
            card_path         TEXT,
            short_url         TEXT,
            status            TEXT DEFAULT 'PENDING',
            published_at      TEXT,
            created_at        TEXT DEFAULT (datetime('now'))
        )
    """)
    # migrate existing DBs that may be missing newer columns
    for col in ("short_url TEXT", "categories TEXT", "tags TEXT"):
        try:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col}")
        except Exception:
            pass  # column already exists
    conn.commit()
    conn.close()
    return db_path


def get_existing_urls(conn):
    rows = conn.execute("SELECT url FROM articles").fetchall()
    return {row["url"] for row in rows}


def insert_article(conn, article: dict):
    article.setdefault("id", str(uuid.uuid4()))
    article.setdefault("status", "PENDING")
    article.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    conn.execute(
        """
        INSERT OR IGNORE INTO articles
            (id, source, headline, url, scraped_content, category, categories, tags,
             summary, word_count, article_image_url, card_path, short_url, status, created_at)
        VALUES
            (:id, :source, :headline, :url, :scraped_content, :category, :categories, :tags,
             :summary, :word_count, :article_image_url, :card_path, :short_url, :status, :created_at)
        """,
        article,
    )
    conn.commit()


def get_articles_by_status(conn, status="PENDING"):
    return conn.execute(
        "SELECT * FROM articles WHERE status = ? ORDER BY created_at DESC",
        (status,),
    ).fetchall()


def get_all_articles(conn):
    return conn.execute(
        "SELECT * FROM articles ORDER BY created_at DESC"
    ).fetchall()


def update_status(conn, article_id: str, status: str):
    conn.execute(
        "UPDATE articles SET status = ? WHERE id = ?",
        (status, article_id),
    )
    conn.commit()


def update_summary(conn, article_id: str, summary: str):
    conn.execute(
        "UPDATE articles SET summary = ? WHERE id = ?",
        (summary, article_id),
    )
    conn.commit()
