# AI News Aggregator — Project Guidebook

> **Living document.** Updated at the end of every completed stage.
> Last updated: Stage 3 complete.

---

## Table of Contents

1. [What This Project Does](#1-what-this-project-does)
2. [Tech Stack](#2-tech-stack)
3. [Prerequisites](#3-prerequisites)
4. [Getting Started From Scratch](#4-getting-started-from-scratch)
5. [Project Structure](#5-project-structure)
6. [Environment Variables](#6-environment-variables)
7. [Stage 1 — Initialization & Infrastructure](#7-stage-1--initialization--infrastructure)
8. [Stage 2 — Database Layer & Repository](#8-stage-2--database-layer--repository)
9. [Stage 3 — Scrapers & Enrichment](#9-stage-3--scrapers--enrichment-not-yet-built)
10. [Stage 4 — AI Agent Architecture](#10-stage-4--ai-agent-architecture-not-yet-built)
11. [Stage 5 — Pipeline Orchestration & Email Delivery](#11-stage-5--pipeline-orchestration--email-delivery-not-yet-built)
12. [Stage 6 — Deployment on Render](#12-stage-6--deployment-on-render-not-yet-built)
13. [Database Schema Reference](#13-database-schema-reference)
14. [How to Run Locally](#14-how-to-run-locally)
15. [Key Design Decisions](#15-key-design-decisions)
16. [Common Pitfalls](#16-common-pitfalls)

---

## 1. What This Project Does

A fully automated daily newsletter pipeline:

1. **Scrapes** the latest AI content from YouTube channels (OpenAI, Anthropic, Google DeepMind, etc.), the OpenAI blog RSS feed, and the Anthropic blog RSS feeds.
2. **Enriches** each item — fetches YouTube transcripts and converts Anthropic HTML articles to Markdown.
3. **Digests** each item using an AI agent (OpenAI Structured Outputs) to produce a short title and 2–3 sentence summary.
4. **Curates** the digests by ranking them against a personal interest profile (`user_profile.json`).
5. **Composes** a personalized HTML email with a greeting and ranked article list.
6. **Sends** the email via Gmail SMTP once per day.
7. **Marks** sent items in the database so they are never re-sent.

Everything runs as a single cron job on Render (or locally on demand).

---

## 2. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Modern type hints, good async/sync ecosystem |
| Package manager | `uv` | Fast, lockfile-based, reproducible |
| Database | PostgreSQL 17 | Reliable, great with SQLAlchemy |
| ORM | SQLAlchemy 2.0 (sync) | Mapped/mapped_column style, mature |
| Config | `pydantic-settings` | `.env` loading with type validation |
| AI | OpenAI Responses API | Structured Outputs for reliable parsing |
| Scraping | `requests`, `beautifulsoup4`, `html2text` | Lightweight, no JS rendering needed |
| YouTube | `youtube-transcript-api` | Handles transcript fetching + proxy support |
| Email | Python `smtplib` (Gmail SMTP) | Simple, no extra service needed |
| Deployment | Render Blueprint | Free tier supports Postgres + Cron Job |

---

## 3. Prerequisites

| Tool | Minimum Version | Notes |
|---|---|---|
| Python | 3.12 | Installed at `C:\...\Python314\python.exe` on this machine |
| uv | 0.11+ | Not on PATH — run as `python -m uv` |
| Docker Desktop | Any recent | For local Postgres only |
| OpenAI API key | — | Needs access to `gpt-4o` or better |
| Gmail account | — | Needs an App Password (not your login password) |

### Installing uv (if missing)

```bash
python -m pip install uv
```

---

## 4. Getting Started From Scratch

```bash
# 1. Clone or enter the project folder
cd "AI News Aggregator"

# 2. Create .env from template
cp .env.template .env
# Fill in OPENAI_API_KEY, MY_EMAIL, MY_EMAIL_APP_PASSWORD

# 3. Install dependencies into .venv
python -m uv sync

# 4. Start local Postgres
docker compose -f docker/docker-compose.yml up -d

# 5. Create the database tables
.venv/Scripts/python.exe -m app.database.init_db

# 6. Run the pipeline
python -m uv run python main.py
```

---

## 5. Project Structure

```
AI News Aggregator/
│
├── main.py                         # Single entry point (cron runs this)
├── pyproject.toml                  # Dependencies & project metadata
├── uv.lock                         # Locked dependency tree
├── .env                            # Secrets — never commit
├── .env.template                   # Placeholder file — commit this
├── .python-version                 # Pins Python 3.12 for uv
├── CLAUDE.md                       # Instructions for Claude Code
├── Guidebook.md                    # ← You are here
│
├── app/
│   ├── __init__.py
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py               # SQLAlchemy ORM table definitions
│   │   ├── connection.py           # Engine, SessionLocal, Settings
│   │   ├── repository.py           # All DB read/write logic
│   │   └── init_db.py              # One-time schema creation script
│   │
│   ├── scrapers/                   # [Stage 3]
│   │   ├── __init__.py
│   │   ├── base.py                 # Shared RSS parsing helpers
│   │   ├── youtube.py              # YouTube feed + transcript fetcher
│   │   ├── openai_scraper.py       # OpenAI blog RSS
│   │   └── anthropic_scraper.py    # Anthropic blog RSS (3 feeds)
│   │
│   ├── agents/                     # [Stage 4]
│   │   ├── __init__.py
│   │   ├── base.py                 # Shared OpenAI client + structured output helper
│   │   ├── digest.py               # DigestAgent: article → title + summary
│   │   ├── curator.py              # CuratorAgent: digests + profile → ranked list
│   │   └── email_agent.py          # EmailAgent: ranked digests → HTML email body
│   │
│   └── services/                   # [Stage 5]
│       ├── __init__.py
│       └── pipeline.py             # Orchestrates all steps end-to-end
│
└── docker/
    └── docker-compose.yml          # Postgres 17 for local development
```

---

## 6. Environment Variables

Defined in `.env` (copy from `.env.template`). Loaded by `pydantic-settings` in `app/database/connection.py`.

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `DATABASE_URL` | Yes | Full Postgres connection string |
| `MY_EMAIL` | Yes | Gmail address used to send the newsletter |
| `MY_EMAIL_APP_PASSWORD` | Yes | Gmail App Password (Settings → Security → 2FA → App passwords) |

**Local default for `DATABASE_URL`:**
```
postgresql://postgres:postgres@localhost:5432/ai_news_aggregator
```

---

## 7. Stage 1 — Initialization & Infrastructure

**Status: Complete**

### What was done

- Initialized with `uv init` — created `pyproject.toml`, `.python-version`, `.gitignore`, `.venv`
- Created all package directories with `__init__.py` files
- Added all 9 production dependencies via `uv add`
- Created `docker/docker-compose.yml` for Postgres 17
- Created `.env.template` with all required placeholders
- Stubbed `main.py` to call `app.services.pipeline.run_pipeline()`

### Key files

| File | Purpose |
|---|---|
| [pyproject.toml](pyproject.toml) | Project metadata + locked dependencies |
| [docker/docker-compose.yml](docker/docker-compose.yml) | Local Postgres 17 container |
| [.env.template](.env.template) | Credential placeholders |
| [main.py](main.py) | Entry point |

### Dependencies installed

```
sqlalchemy          beautifulsoup4      openai
psycopg2-binary     html2text           python-dotenv
pydantic-settings   requests            youtube-transcript-api
```

---

## 8. Stage 2 — Database Layer & Repository

**Status: Complete**

### What was done

Four files make up the entire database layer:

---

#### `app/database/models.py`

Four SQLAlchemy 2.0 ORM models using `Mapped` / `mapped_column` style.

| Model | Table | Natural key | Notable columns |
|---|---|---|---|
| `YouTubeVideo` | `youtube_videos` | `video_id` (String 20) | `transcript` (Text, nullable), `transcript_status` (pending/done/unavailable) |
| `OpenAIArticle` | `openai_articles` | `guid` (String 500) | `description` (Text, nullable) |
| `AnthropicArticle` | `anthropic_articles` | `guid` (String 500) | `markdown_content` (Text, nullable) |
| `Digest` | `digests` | `id` (auto PK) | `article_id` (int), `article_type`, `score` (float), `sent_at` (nullable) |

**Design rules applied:**
- All `DateTime` columns use `timezone=True` — no naive datetimes anywhere
- `created_at` uses `server_default=func.now()` (set by Postgres, not Python)
- `Digest.article_id` is an `int` pointing to the source row's `id`
- No SQLAlchemy `ForeignKey` constraints — article rows across three tables would need a polymorphic FK, kept simple intentionally

---

#### `app/database/connection.py`

```python
settings = Settings()   # loads .env via pydantic-settings
engine   = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(...)
get_db_session() -> Session   # returns a plain session (caller uses 'with')
```

`pool_pre_ping=True` — before handing out a connection from the pool, SQLAlchemy pings Postgres. Prevents "connection reset" errors after Postgres restarts (common on Render's free tier).

---

#### `app/database/repository.py`

Single `Repository` class. Injected with a `Session`, gives the pipeline a clean API over the DB.

| Method | Description |
|---|---|
| `add_youtube_video(data)` | Insert or return existing. Returns `(video, created: bool)` |
| `get_pending_transcripts()` | Videos with `transcript_status = 'pending'` |
| `update_transcript(video_id, text, status)` | Sets transcript + status |
| `get_videos_without_digests()` | Done-transcript videos with no digest yet |
| `add_openai_article(data)` | Insert or return existing. Returns `(article, created: bool)` |
| `get_openai_articles_without_digests()` | Articles with no digest row yet |
| `add_anthropic_article(data)` | Insert or return existing. Returns `(article, created: bool)` |
| `update_anthropic_markdown(id, md)` | Sets markdown_content after enrichment |
| `get_anthropic_articles_without_digests()` | Articles with no digest row yet |
| `add_digest(data)` | Insert a new digest row |
| `get_unsent_digests(hours, limit)` | Unsent digests from last N hours, ranked by score |
| `mark_digests_sent(ids)` | Bulk-sets `sent_at = now()` for a list of IDs |
| `commit()` / `rollback()` | Explicit transaction control for the pipeline |

**Transaction pattern:**
- All `add_*` / `update_*` calls use `flush()` not `commit()` — they stage changes
- The pipeline calls `repo.commit()` once at the end of each logical step
- On error the pipeline calls `repo.rollback()`

**Deduplication:**
- `add_youtube_video` checks `video_id` before inserting
- `add_openai_article` / `add_anthropic_article` check `guid` before inserting
- "Without digests" queries use correlated `EXISTS` subqueries — no Python-side filtering

---

#### `app/database/init_db.py`

```bash
# Run once after setting up .env and starting Postgres
.venv/Scripts/python.exe -m app.database.init_db
```

Calls `Base.metadata.create_all()` — idempotent, safe to re-run.

---

## 9. Stage 3 — Scrapers & Enrichment

**Status: Complete**

### What was done

---

#### `app/scrapers/base.py`

Shared primitives imported by all scrapers.

| Export | Description |
|---|---|
| `VideoItem` | Pydantic model — video_id, title, url, published_at |
| `ArticleItem` | Pydantic model — guid, title, url, description (opt), published_at |
| `fetch_feed(url)` | `requests.get` → `ET.fromstring` root element (no lxml needed) |
| `parse_date(raw)` | RFC 2822 → ISO 8601 → now(UTC) cascade; always returns tz-aware UTC |
| `HEADERS` | Browser-like User-Agent used by all HTTP calls |
| `BaseScraper` | Abstract base; enforces `scrape_metadata() -> list` |

**RSS parsing**: uses Python's built-in `xml.etree.ElementTree` — lxml is not required.

---

#### `app/scrapers/youtube.py`

`YouTubeScraper(channel_id, channel_name)`

| Method | Description |
|---|---|
| `scrape_metadata()` | Parses Atom feed (`YT_NS` namespaces), skips `/shorts/`, returns `VideoItem` list |
| `fetch_transcript(video_id)` | Returns `(text, "done")` or `(None, "unavailable")` |
| `_get_api()` | Lazy-init `YouTubeTranscriptApi`; uses `WebshareProxyConfig` if env vars set |

**Transcript error handling**: `NoTranscriptFound`, `TranscriptsDisabled`, `IpBlocked`, `RequestBlocked`, `CouldNotRetrieveTranscript` and any `Exception` all resolve to `"unavailable"` — the pipeline never retries a broken video.

**Proxy**: `WEBSHARE_USERNAME` / `WEBSHARE_PASSWORD` in `.env` enable the Webshare rotating proxy. If absent, no proxy is used. The API instance is lazy and reused across calls.

---

#### `app/scrapers/ai_news.py`

**`fetch_article_markdown(url)`** — standalone utility:
1. `requests.get(url)` with browser headers
2. Strip `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, `<aside>`, `<noscript>`
3. Find article body: `<article>` → `<main>` → `.content` class → `<body>`
4. `html2text` with `ignore_images=True`, `body_width=0` (no hard wrapping)
5. Returns `None` on network error or Cloudflare block (logs a warning)

**`OpenAIScraper`** — RSS 2.0 from `https://openai.com/news/rss.xml`
- Falls back to link URL when `<guid>` is missing

**`AnthropicScraper`** — aggregates three feeds:
- `https://www.anthropic.com/rss/news.xml`
- `https://www.anthropic.com/rss/engineering.xml`
- `https://www.anthropic.com/rss/research.xml`
- Deduplicates by GUID in Python after collecting all feeds
- One feed failing does not stop the others

---

#### `app/services/scrapers.py`

`ScraperService(repo, youtube_channels=None)`

**`run_metadata() -> dict`**
- Calls all scrapers, saves new rows via `repo.add_*()`, commits once at the end
- Returns `{"youtube": N, "openai": N, "anthropic": N}` (new rows only)

**`run_enrichment() -> dict`**
- **Transcripts**: queries `get_pending_transcripts()`, calls `scraper.fetch_transcript()`, calls `repo.update_transcript()`, commits per video
- **Markdown**: queries `get_anthropic_articles_pending_markdown()`, calls `fetch_article_markdown()`, calls `repo.update_anthropic_markdown()`, commits per article
- Each item commits individually — one failure rolls back only that item
- Returns `{"transcripts_done", "transcripts_unavailable", "markdown_done", "markdown_failed"}`

**`DEFAULT_YOUTUBE_CHANNELS`** — list of `(channel_id, name)` tuples for OpenAI, Anthropic, Google DeepMind. Update this constant to add/remove channels.

---

#### Repository additions (Stage 3)

- `get_anthropic_articles_pending_markdown()` — added to `repository.py`: returns `AnthropicArticle` rows where `markdown_content IS NULL`

#### Settings additions (Stage 3)

- `WEBSHARE_USERNAME: str = ""` and `WEBSHARE_PASSWORD: str = ""` added to `Settings` in `connection.py`
- Both added to `.env.template` under a `# Webshare` section

---

## 10. Stage 4 — AI Agent Architecture *(not yet built)*

### Planned files

**`app/agents/base.py`** — `BaseAgent`
- Initializes the OpenAI client once (`openai.OpenAI(api_key=settings.OPENAI_API_KEY)`)
- Provides a generic `call(prompt, response_model)` method using Structured Outputs
- All agents inherit from this

**`app/agents/digest.py`** — `DigestAgent`
- Input: article text or YouTube transcript (as string)
- Output (Pydantic model): `digest_title: str`, `digest_summary: str` (2–3 sentences)
- Used per-article after enrichment

**`app/agents/curator.py`** — `CuratorAgent`
- Input: list of `Digest` rows + `user_profile.json`
- Output (Pydantic model): list of `{digest_id, score, reasoning}`
- Updates `score` on each digest row

**`app/agents/email_agent.py`** — `EmailAgent`
- Input: top-N ranked `Digest` rows
- Output (Pydantic model): `greeting: str`, `intro: str`, `html_body: str`
- The HTML body contains all article sections, formatted for email

### `user_profile.json` (to be created in root)
```json
{
  "name": "...",
  "interests": ["LLMs", "AI safety", "multimodal models", "..."],
  "preferred_depth": "technical",
  "preferred_length": "concise"
}
```

---

## 11. Stage 5 — Pipeline Orchestration & Email Delivery *(not yet built)*

### Planned file: `app/services/pipeline.py`

The `run_pipeline()` function is the only thing `main.py` calls.

**Execution order:**

```
Step 1 — Scrape metadata
  └─ YouTube: save video rows (transcript_status=pending)
  └─ OpenAI: save article rows
  └─ Anthropic: save article rows

Step 2 — Enrich
  └─ Fetch transcripts for all pending YouTube videos
  └─ Fetch + convert Anthropic article HTML → Markdown

Step 3 — Digest
  └─ For each video with status=done and no digest → DigestAgent
  └─ For each OpenAI article with no digest → DigestAgent
  └─ For each Anthropic article with no digest → DigestAgent

Step 4 — Curate
  └─ CuratorAgent ranks all unsent digests from last 24h
  └─ Updates score on each Digest row

Step 5 — Compose email
  └─ EmailAgent generates HTML from top-N digests

Step 6 — Send
  └─ smtplib sends via Gmail SMTP (TLS, port 587)

Step 7 — Mark sent
  └─ repo.mark_digests_sent([ids])
  └─ repo.commit()
```

**Gmail SMTP snippet (for reference):**
```python
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
    smtp.starttls()
    smtp.login(settings.MY_EMAIL, settings.MY_EMAIL_APP_PASSWORD)
    smtp.sendmail(from_addr, to_addr, msg.as_string())
```

---

## 12. Stage 6 — Deployment on Render *(not yet built)*

### Planned files

**`render.yaml`** — Render Blueprint
```yaml
services:
  - type: cron
    name: ai-news-aggregator
    runtime: docker
    schedule: "0 7 * * *"   # 7am UTC daily
    dockerfilePath: ./Dockerfile

databases:
  - name: ai-news-aggregator-db
    databaseName: ai_news_aggregator
    plan: free
```

**`Dockerfile`** — Multi-stage build with uv
```dockerfile
FROM python:3.12-slim AS builder
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /app/.venv .venv
COPY . .
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "main.py"]
```

**Required environment variables on Render:**

| Variable | Where to set |
|---|---|
| `DATABASE_URL` | Auto-injected by Render when you link the Postgres database |
| `OPENAI_API_KEY` | Render dashboard → Environment |
| `MY_EMAIL` | Render dashboard → Environment |
| `MY_EMAIL_APP_PASSWORD` | Render dashboard → Environment |

---

## 13. Database Schema Reference

### `youtube_videos`

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PK, autoincrement |
| `video_id` | VARCHAR(20) | UNIQUE, NOT NULL, indexed |
| `title` | VARCHAR(500) | NOT NULL |
| `url` | VARCHAR(200) | NOT NULL |
| `published_at` | TIMESTAMPTZ | NOT NULL |
| `transcript` | TEXT | nullable |
| `transcript_status` | VARCHAR(20) | NOT NULL, default `pending` |
| `created_at` | TIMESTAMPTZ | NOT NULL, server default `now()` |

### `openai_articles`

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PK, autoincrement |
| `guid` | VARCHAR(500) | UNIQUE, NOT NULL, indexed |
| `title` | VARCHAR(500) | NOT NULL |
| `url` | VARCHAR(500) | NOT NULL |
| `description` | TEXT | nullable |
| `published_at` | TIMESTAMPTZ | NOT NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL, server default `now()` |

### `anthropic_articles`

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PK, autoincrement |
| `guid` | VARCHAR(500) | UNIQUE, NOT NULL, indexed |
| `title` | VARCHAR(500) | NOT NULL |
| `url` | VARCHAR(500) | NOT NULL |
| `markdown_content` | TEXT | nullable |
| `published_at` | TIMESTAMPTZ | NOT NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL, server default `now()` |

### `digests`

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PK, autoincrement |
| `article_id` | INTEGER | NOT NULL, indexed — points to source row's `id` |
| `article_type` | VARCHAR(20) | NOT NULL — `youtube` / `openai` / `anthropic` |
| `digest_title` | VARCHAR(500) | NOT NULL |
| `digest_summary` | TEXT | NOT NULL |
| `score` | FLOAT | NOT NULL, default `0.0` |
| `sent_at` | TIMESTAMPTZ | nullable — NULL = not yet sent |
| `created_at` | TIMESTAMPTZ | NOT NULL, server default `now()` |

---

## 14. How to Run Locally

### Start / stop Postgres

```bash
# Start
docker compose -f docker/docker-compose.yml up -d

# Stop (keeps data)
docker compose -f docker/docker-compose.yml stop

# Stop + destroy data volume
docker compose -f docker/docker-compose.yml down -v
```

### Initialize schema (first time only)

```bash
.venv/Scripts/python.exe -m app.database.init_db
```

### Run the full pipeline

```bash
python -m uv run python main.py
```

### Add a new dependency

```bash
python -m uv add <package-name>
```

### Connect to the local DB (psql)

```bash
docker exec -it ai_news_aggregator_db psql -U postgres -d ai_news_aggregator
```

---

## 15. Key Design Decisions

| Decision | Reasoning |
|---|---|
| Sync SQLAlchemy (not async) | The pipeline is a batch job, not a web server. Sync is simpler with no async overhead. |
| `flush()` inside repo, `commit()` by the pipeline | One transaction per pipeline step. If step 3 fails, steps 1–2 are still committed. If step 3 partially fails, the whole step rolls back atomically. |
| `(object, created: bool)` return from `add_*` | Caller knows without a second query whether an item was new. Useful for logging/metrics. |
| No SQLAlchemy FK constraints on `Digest.article_id` | Articles live in three separate tables. A polymorphic FK would complicate the schema. Integrity is enforced at the application layer by the pipeline. |
| Correlated `EXISTS` for "without digests" queries | More efficient than a `LEFT JOIN ... WHERE id IS NULL` pattern at scale. |
| `server_default=func.now()` (not Python `default`) | DB sets the timestamp — consistent even if the app clock drifts, and works correctly in bulk inserts. |
| All datetimes timezone-aware (`TIMESTAMPTZ`) | Avoids bugs when Render and local dev run in different timezones. |
| Structured Outputs for all agents | Guarantees a parseable response every call. No regex, no JSON extraction, no retries for format failures. |

---

## 16. Common Pitfalls

| Pitfall | What happens | Fix |
|---|---|---|
| Running `uv` directly in the terminal | `command not found` | Use `python -m uv` — uv is not on PATH on this machine |
| Committing `.env` | Secrets in git history | `.gitignore` already excludes it — only commit `.env.template` |
| Using `datetime.utcnow()` | DeprecationWarning in Python 3.12+; returns naive datetime | Use `datetime.now(timezone.utc)` everywhere |
| Adding Shorts to the DB | Wasted transcript fetch attempts | YouTubeScraper must filter URLs containing `/shorts/` before saving |
| Calling `commit()` inside every repo method | Nested transaction issues; no rollback possible for a step | Use `flush()` inside methods, `commit()` only from the pipeline |
| Forgetting `pool_pre_ping` on Render | First request after idle kills the connection | Already set in `connection.py` |
| Generating free-form OpenAI responses | Unparseable output crashes the pipeline | All agent calls must pass a Pydantic `response_format` model |
