# Briefly — Project Context & Architecture

## What is Briefly?
An automated news aggregation app inspired by Inshorts. Scrapes Canadian and North American RSS feeds, summarizes articles into 60–65 words using a local LLM, generates visual news cards, and distributes them via a mobile app, Telegram, and Instagram.

---

## Pipeline (in order)

1. **RSS Ingestion** — fetch feeds, scrape full article text, deduplicate against Supabase
2. **LLM Processing** — tag category + summarize + QA in a single stateless Ollama call
3. **Image extraction** — pull article photo from RSS or og:image meta tag
4. **Card generation** — create 1080×1350px JPG with photo, headline, summary
5. **Human review** — approve / reject / edit via local FastAPI dashboard
6. **Publish** — push approved articles + cards to Supabase, trigger Expo push notification

### Scheduling
- Runs at **6 AM daily** via Mac cron job
- GitHub Actions as cloud fallback (free tier, ~2–3 min runtime)
- All processing happens **in memory** — no local database

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Ingestion | feedparser, trafilatura, requests | RSS + article scraping |
| Scheduling | cron (Mac) → GitHub Actions | 6 AM daily |
| LLM | Ollama + Qwen 2.5 14B | Local, stateless, one call per article |
| Card gen | Python Pillow | 1080×1350px, ~80KB compressed |
| Review UI | FastAPI + HTML | Local browser dashboard |
| Cloud DB | Supabase PostgreSQL | Articles, cards, status, categories |
| File storage | Supabase Storage | Card JPGs via CDN URL |
| App API | Supabase REST | Auto-generated, no extra backend needed |
| Push notifs | Expo Push Service | No Firebase needed |
| Mobile app | React Native + Expo | iOS + Android, single codebase |
| Telegram | python-telegram-bot | Auto-posts card + summary |
| Instagram | Meta Graph API | Semi-automated, business account required |

### Key decisions
- **No local database** — deduplicate by loading existing URLs from Supabase into a Python set at run start
- **No Firebase** — Supabase handles DB + storage + REST API; Expo handles push notifications natively
- **No multi-model architecture** — one Qwen 2.5 14B call returns JSON with category + summary + word_count + qa_pass
- **Sequential processing** — 16GB RAM fits one model; multi-model would require model swapping overhead
- **Cards generated server-side** — app displays pre-generated JPGs, no compute on mobile

---

## Ollama LLM Call

Single prompt per article returns structured JSON:

```json
{
  "category": "politics | tech | finance | science | world | sports",
  "summary": "60–65 word summary in North American journalism style",
  "word_count": 62,
  "qa_pass": true
}
```

- Model: `qwen2.5:14b`
- One stateless call per article — no conversation history passed
- Skip article if scraped content < 200 chars (insufficient to summarize)
- Context window: 32K tokens — single article (~3K chars) is well within limit

---

## Card Design (Pillow)

- Size: 1080 × 1350px (Instagram portrait / Story compatible)
- Top 40%: article photo (from RSS or og:image)
- Below photo: headline in bold white
- Lower section: 60-word summary in lighter text
- Category tag pill (e.g. "Tech", "Politics")
- Compressed to ~80KB at quality=75

---

## Supabase Schema (proposed)

### articles table
```sql
id              uuid primary key
source          text                        -- e.g. "CBC News"
headline        text
url             text unique                 -- used for deduplication
scraped_content text
category        text                        -- politics/tech/finance/science/world/sports
summary         text                        -- 60-65 word AI summary
article_image_url text
card_url        text                        -- Supabase Storage CDN URL
status          text default 'PENDING'      -- PENDING / APPROVED / REJECTED
published_at    timestamptz
created_at      timestamptz default now()
```

---

## RSS Feeds

| Source | Feed URL |
|---|---|
| CBC News | https://rss.cbc.ca/lineup/topstories.xml |
| CTV News | https://www.ctvnews.ca/rss/ctvnews-ca-top-stories-public-rss-1.822009 |
| Global News | https://globalnews.ca/feed/ |
| CP24 | https://www.cp24.com/rss/cp24 |
| Financial Post | https://financialpost.com/feed/ |
| BNN Bloomberg | https://www.bnnbloomberg.ca/arc/outboundfeeds/rss/ |
| Reuters | https://feeds.reuters.com/reuters/topNews |
| AP News | https://rsshub.app/apnews/topics/apf-topnews |
| TechCrunch | https://techcrunch.com/feed/ |

---

## File Structure

```
/briefly
  BRIEFLY.md              ← this file
  requirements.txt
  ingest.py               ← RSS scraping + deduplication
  llm.py                  ← Ollama summarize/tag/QA
  card_gen.py             ← Pillow card generation
  publish.py              ← Supabase upload + Expo push
  review/
    main.py               ← FastAPI review dashboard
    templates/
      index.html
  .env                    ← SUPABASE_URL, SUPABASE_KEY, OLLAMA_HOST
  .github/
    workflows/
      daily.yml           ← GitHub Actions fallback scheduler
```

---

## Environment Variables

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your-service-role-key
OLLAMA_HOST=http://localhost:11434
MAX_PER_FEED=5
SHEET_NAME=News
```

---

## Legal Notes
- Always link back to source article
- Summaries kept under 65 words — transformative use
- Check robots.txt before scraping — skip sources that disallow
- Wire services (Reuters, AP) lowest legal risk
- Add takedown contact email before public launch
- Consult lawyer before monetising

---

## What's Already Built (Colab prototype)
- RSS ingestion with feedparser + requests (working)
- Article scraping with trafilatura (working)
- Deduplication against Google Sheets (working)
- Gemini summarization — replaced with local Ollama
- Card generation with Pillow (working)
- Google Drive card upload (working)
- Google Sheets as CMS (replaced by Supabase)
