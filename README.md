# Briefly

An automated news aggregation pipeline inspired by Inshorts. Scrapes Canadian and North American RSS feeds, summarizes articles into 60–65 words using a local LLM, generates visual news cards, and distributes them via mobile app, Telegram, and Instagram.

---

## How it works

1. Runs at **6 AM daily** via cron on a Mac M4
2. Fetches 9 RSS feeds, scrapes full article text
3. Local LLM (Qwen 2.5 14B via Ollama) tags category + summarizes + QA checks each article in one call
4. Pillow generates a 1080×1350px news card (photo + headline + summary)
5. Human reviews and approves via a local FastAPI dashboard
6. Approved cards pushed to Supabase; push notification sent via Expo

---

## Stack

- **Ingestion** — feedparser, trafilatura, requests
- **LLM** — Ollama + Qwen 2.5 14B (local, no API cost)
- **Card generation** — Python Pillow
- **Review dashboard** — FastAPI + HTML
- **Cloud** — Supabase (PostgreSQL + Storage + REST API)
- **Mobile** — React Native + Expo
- **Distribution** — Telegram (python-telegram-bot), Instagram (Meta Graph API)

---

## Project structure

```
/briefly
  BRIEFLY.md              ← full architecture and decisions
  README.md               ← this file
  requirements.txt
  ingest.py               ← RSS scraping + deduplication
  llm.py                  ← Ollama tag + summarize + QA
  card_gen.py             ← Pillow card generation
  publish.py              ← Supabase upload + Expo push
  review/
    main.py               ← FastAPI review dashboard
    templates/
      index.html
  .env                    ← credentials (never commit)
  .github/
    workflows/
      daily.yml           ← GitHub Actions fallback scheduler
```

---

## Setup

### Prerequisites
- Mac with [Ollama](https://ollama.ai) installed
- Qwen 2.5 14B pulled: `ollama pull qwen2.5:14b`
- [Supabase](https://supabase.com) project created
- Python 3.11+

### Install dependencies
```bash
pip install feedparser trafilatura requests pillow fastapi uvicorn supabase python-telegram-bot
```

### Environment variables
Create a `.env` file:
```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your-service-role-key
OLLAMA_HOST=http://localhost:11434
MAX_PER_FEED=5
```

### Supabase table
```sql
create table articles (
  id                uuid primary key default gen_random_uuid(),
  source            text,
  headline          text,
  url               text unique,
  scraped_content   text,
  category          text,
  summary           text,
  article_image_url text,
  card_url          text,
  status            text default 'PENDING',
  published_at      timestamptz,
  created_at        timestamptz default now()
);
```

### Run manually
```bash
python ingest.py        # scrape + summarize + generate cards
uvicorn review.main:app # open review dashboard at localhost:8000
python publish.py       # push approved articles to Supabase
```

### Schedule via cron (6 AM daily)
```bash
crontab -e
0 6 * * * cd /path/to/briefly && python ingest.py
```

---

## RSS feeds

| Source | Category |
|---|---|
| CBC News | Canadian general |
| CTV News | Canadian general |
| Global News | Canadian general |
| CP24 | GTA breaking news |
| Financial Post | Business / finance |
| BNN Bloomberg | Markets |
| Reuters | World |
| AP News | World |
| TechCrunch | Technology |

---

## Legal

- All articles link back to original source
- Summaries are 60–65 words (transformative use)
- robots.txt respected — sources that disallow scraping are skipped
- Add a takedown contact before public launch
- Consult a lawyer before monetising
