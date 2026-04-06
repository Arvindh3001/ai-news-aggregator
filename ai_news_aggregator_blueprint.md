# AI News Aggregator: Complete Implementation Blueprint

Goal: A daily, personalized AI news email (top articles + YouTube videos) based on a user profile.

## Tech Stack
- **Backend**: Python 3.12+ (managed with `uv`)
- **Database**: PostgreSQL 17 (SQLAlchemy 2.0 ORM)
- **AI Engine**: OpenAI Responses API (Structured Outputs)
- **Scraping**: RSS, `youtube-transcript-api`, `requests`, `html2text`
- **Deployment**: Render Blueprint (Postgres + Cron Job)

---

## Stage 1: Project Initialization & Infrastructure
- Initialize with `uv init`.
- Create `docker/docker-compose.yml` for local Postgres.
- Setup `.env` template.
- **Dependencies**: `sqlalchemy`, `psycopg2-binary`, `pydantic-settings`, `openai`, `youtube-transcript-api`, `requests`, `html2text`, `python-dotenv`, `beautifulsoup4`.

## Stage 2: Database Layer & Repository
- **Models** (`app/database/models.py`):
    - `youtube_videos`: `video_id` (PK), `title`, `url`, `published_at`, `transcript`, `transcript_status` (pending/done/unavailable).
    - `openai_articles`: `guid` (PK), `title`, `url`, `description`, `published_at`.
    - `anthropic_articles`: `guid` (PK), `title`, `url`, `markdown_content`, `published_at`.
    - `digests`: `id`, `article_id`, `article_type`, `digest_title`, `digest_summary`, `score`, `sent_at`.
- **Repository** (`app/database/repository.py`):
    - Generic CRUD operations.
    - Specialized queries: "get videos without transcripts", "get articles without digests", "get unsent digests from last 24h".

## Stage 3: Scrapers & Enrichment Logic
- **BaseScraper**: Common logic for RSS parsing and data validation.
- **YouTubeScraper**:
    - URL parsing (skipping Shorts).
    - RSS endpoint: `https://www.youtube.com/feeds/videos.xml?channel_id=ID`.
    - Transcript fetching via `youtube-transcript-api` (supporting Webshare proxies).
- **OpenAIScraper**: RSS parsing from official feed.
- **AnthropicScraper**: Aggregating news, engineering, and research feeds (via community RSS).
- **Enrichment Services**: HTML-to-Markdown conversion for Anthropic articles.

## Stage 4: AI Agent Architecture
- **BaseAgent**: Shared OpenAI client setup with structured response parsing.
- **DigestAgent**:
    - Input: Article text/transcript.
    - Output: Title + 2-3 sentence summary.
- **CuratorAgent**:
    - Input: List of digests + `user_profile.json`.
    - Output: Ranked list with relevance scores and reasoning.
- **EmailAgent**:
    - Input: Top N digests.
    - Output: Personalized greeting, intro, and HTML-structured content.

## Stage 5: Pipeline Orchestration & Email Delivery
- **Runner** (`app/services/pipeline.py`):
    1. Scrape latest metadata (fast).
    2. Enrich items (transcripts/markdown).
    3. Generate new digests for enriched items.
    4. Rank & Crate daily email.
    5. Send via SMTP (Gmail App Password).
    6. Mark items as `sent_at` in DB.
- **Main Entry** (`main.py`): Logic to check environment (Local vs Production) and run the pipeline.

## Stage 6: Deployment (Render)
- `render.yaml`: Blueprint for Postgres and Cron Job.
- `Dockerfile`: Multi-stage build with `uv`.
- Environment Variables: `OPENAI_API_KEY`, `DATABASE_URL`, `MY_EMAIL`, `EMAIL_APP_PASSWORD`.

---

## Detailed Requirements Checklist
- [ ] No duplicated database entries (use PKs/GUIDs).
- [ ] Handle missing transcripts gracefully (mark as "unavailable").
- [ ] Efficient HTML-to-Markdown (use `html2text`).
- [ ] Rotating proxies for YouTube transcripts.
- [ ] Structured outputs for all agent responses.
- [ ] Personalized intro based on user profile.
- [ ] Single entry point `main.py` for cron execution.
