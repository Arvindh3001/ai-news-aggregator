# AI News Aggregator

A fully automated daily newsletter that scrapes the latest AI content from YouTube, OpenAI, and Anthropic — digests it with GPT-4o-mini, ranks it against your interests, and emails a clean HTML digest to your inbox every morning.

---

## What It Does

```
YouTube channels  ─┐
OpenAI blog RSS   ─┼─► Scrape ─► Enrich ─► Digest ─► Curate ─► Email
Anthropic blog RSS ─┘
```

1. **Scrape** — pulls the latest videos and articles from RSS feeds
2. **Enrich** — fetches YouTube transcripts and converts Anthropic HTML articles to Markdown
3. **Digest** — summarises each item into a punchy title + 2-3 sentence technical summary
4. **Curate** — scores every digest against your interest profile (0.0–1.0)
5. **Email** — sends a ranked HTML email with the top 10 items to your inbox

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Installed at `C:\...\Python314\python.exe` on Windows |
| Docker Desktop | For running Postgres locally |
| OpenAI API key | Needs access to `gpt-4o-mini` |
| Gmail account | Needs a [Gmail App Password](https://myaccount.google.com/apppasswords) — not your login password |

---

## Setup

### 1. Install dependencies

```bash
python -m pip install uv        # install uv if not already installed
python -m uv sync               # creates .venv and installs all packages
```

### 2. Configure environment

```bash
cp .env.template .env
```

Open `.env` and fill in your values:

```env
OPENAI_API_KEY=sk-...
MY_EMAIL=you@gmail.com
MY_EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_news_aggregator

# Optional — Webshare proxies for YouTube transcripts (avoids IP blocks)
WEBSHARE_USERNAME=
WEBSHARE_PASSWORD=
```

### 3. Start Postgres

```bash
docker compose -f docker/docker-compose.yml up -d
```

### 4. Create database tables

```bash
.venv/Scripts/python.exe -m app.database.init_db
```

### 5. Customise your interest profile

Edit [`profiles/user_profile.json`](profiles/user_profile.json):

```json
{
  "name": "Your Name",
  "background": "Your role and technical background",
  "interests": [
    "LLM inference and serving",
    "AI agent frameworks",
    "..."
  ],
  "preferred_depth": "technical"
}
```

### 6. Run

```bash
python -m uv run python main.py
```

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key for all AI agents |
| `MY_EMAIL` | Yes | Gmail address — digest is sent here |
| `MY_EMAIL_APP_PASSWORD` | Yes | Gmail App Password (16-char, not your login password) |
| `DATABASE_URL` | Yes | Postgres connection string |
| `WEBSHARE_USERNAME` | No | Webshare proxy username for transcript fetching |
| `WEBSHARE_PASSWORD` | No | Webshare proxy password |

### YouTube Channels

Edit `DEFAULT_YOUTUBE_CHANNELS` in [`app/services/scrapers.py`](app/services/scrapers.py):

```python
DEFAULT_YOUTUBE_CHANNELS = [
    ("UCXZCJLdBC09xxGZ6gcdrc6A", "OpenAI"),
    ("UCrDwWp7EBBv4NwvScIpBDOA", "Anthropic"),
    ("UCP7jMXSY2xbc3KCAE0MHQ-A", "Google DeepMind"),
    # Add more: ("CHANNEL_ID", "Display Name")
]
```

To find a channel's ID: go to the channel's About page → right-click → View Page Source → search for `"channelId"`.

### Number of Articles in Email

Change `_TOP_N` in [`app/services/pipeline.py`](app/services/pipeline.py) (default: 10).

---

## Project Structure

```
├── main.py                        # Entry point — run this
├── pyproject.toml                 # Dependencies
├── .env                           # Secrets (never commit)
├── .env.template                  # Placeholder — commit this
├── profiles/
│   └── user_profile.json          # Your interests — edit this
├── app/
│   ├── database/
│   │   ├── models.py              # SQLAlchemy ORM models
│   │   ├── connection.py          # Engine + settings
│   │   ├── repository.py          # All DB read/write logic
│   │   └── init_db.py             # One-time schema creation
│   ├── scrapers/
│   │   ├── base.py                # Shared RSS parsing + date utils
│   │   ├── youtube.py             # YouTube feed + transcript fetcher
│   │   └── ai_news.py             # OpenAI + Anthropic scrapers, HTML→Markdown
│   ├── agents/
│   │   ├── base_agent.py          # OpenAI Responses API wrapper
│   │   ├── digest_agent.py        # Article → title + summary + category
│   │   ├── curator_agent.py       # Digests + profile → relevance scores
│   │   └── email_agent.py         # Top articles → subject + greeting
│   └── services/
│       ├── scrapers.py            # Two-stage scraping orchestrator
│       ├── digests.py             # Digest generation + curation orchestrator
│       ├── email.py               # HTML builder + Gmail SMTP sender
│       └── pipeline.py            # Master pipeline — coordinates all steps
└── docker/
    └── docker-compose.yml         # Postgres 17 for local dev
```

---

## How the Pipeline Works

```
main.py
  └── pipeline.run_pipeline()
        │
        ├── 1. ScraperService.run_metadata()
        │       ├── YouTubeScraper   → youtube_videos (transcript_status=pending)
        │       ├── OpenAIScraper    → openai_articles
        │       └── AnthropicScraper → anthropic_articles (markdown_content=null)
        │
        ├── 2. ScraperService.run_enrichment()
        │       ├── fetch transcripts  → youtube_videos (status → done/unavailable)
        │       └── fetch + convert HTML → anthropic_articles.markdown_content
        │
        ├── 3. DigestService.run_generation()
        │       └── DigestAgent (gpt-4o-mini) per article → digests table
        │
        ├── 4. DigestService.run_curation()
        │       └── CuratorAgent → scores all unsent digests vs user profile
        │
        ├── 5. EmailAgent.generate()
        │       └── subject + greeting + sign-off
        │
        ├── 6. EmailService.send_digest()
        │       └── Gmail SMTP (port 587, STARTTLS)
        │
        └── 7. repo.mark_digests_sent()   ← only runs if email succeeded
```

**Failure isolation**: steps 1–4 each fail independently. A scraper crash does not prevent the email from being sent using digests from previous runs. `sent_at` is only written after a confirmed SMTP success — if the email fails, those digests are retried the next day.

---

## Database Tables

| Table | Primary Key | Purpose |
|---|---|---|
| `youtube_videos` | `video_id` | YouTube video metadata + transcript |
| `openai_articles` | `guid` | OpenAI blog articles |
| `anthropic_articles` | `guid` | Anthropic blog articles + markdown body |
| `digests` | `id` | AI-generated summaries with relevance score |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Package manager | uv |
| Database | PostgreSQL 17 + SQLAlchemy 2.0 |
| AI | OpenAI Responses API (`gpt-4o-mini`) — Structured Outputs |
| Scraping | requests, BeautifulSoup4, youtube-transcript-api |
| Email | smtplib + Gmail SMTP |
| Deployment | Render (Postgres + Cron Job) |

---

## Local Development Commands

```bash
# Start Postgres
docker compose -f docker/docker-compose.yml up -d

# Stop Postgres (keeps data)
docker compose -f docker/docker-compose.yml stop

# Wipe and recreate database
docker compose -f docker/docker-compose.yml down -v
.venv/Scripts/python.exe -m app.database.init_db

# Add a new dependency
python -m uv add <package>

# Connect to local DB
docker exec -it ai_news_aggregator_db psql -U postgres -d ai_news_aggregator
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `uv: command not found` | Run as `python -m uv` — uv is not on PATH |
| `SMTP auth failed` | Use a Gmail App Password, not your account password. Enable 2FA first. |
| `No transcripts available` | Video has captions disabled — marked `unavailable`, pipeline continues |
| `No curated digests` | No new enriched articles in the last 24h — pipeline exits gracefully, no email sent |
| `Cloudflare block on Anthropic` | Set `WEBSHARE_USERNAME` / `WEBSHARE_PASSWORD` in `.env` |
| `channel returned 404` | YouTube channel ID is wrong — verify via page source, search `"channelId"` |
