"""
DigestAgent — converts raw article content into a structured digest.

Input:  article title + raw content (transcript or markdown text)
Output: DigestItem with a catchy title, 2-3 sentence technical summary, and category tag.

Content truncation
------------------
gpt-4o-mini has a 128k-token context window.  We cap input content at
MAX_CONTENT_CHARS (≈ 80 000 chars ≈ 20 000 tokens) to stay well clear of the
limit and keep latency low.  For a YouTube transcript this usually means the
first ~30-40 minutes of speech is preserved — enough to cover any single video.
The truncation point is appended with a note so the model knows content was cut.
"""
import logging

from pydantic import BaseModel, Field

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# ~20 000 tokens at 4 chars/token — safe ceiling for gpt-4o-mini
MAX_CONTENT_CHARS = 80_000

_SYSTEM_PROMPT = """\
You are a senior AI/ML engineer who writes a daily digest for a technically sophisticated audience.

Your task: read the article or transcript provided and produce a structured digest.

Rules:
- `title`: Write a new, specific, punchy headline (not a copy of the original title).
  Lead with the most interesting technical finding or announcement.
- `summary`: 2-3 sentences.  Be precise and concrete — include model names, benchmark
  numbers, technique names, and architectural details wherever the source provides them.
  Remove marketing language, hype, and filler.  Never start with "The article discusses".
- `category`: One lowercase word that best classifies the content.
  Choose from: research, product, infrastructure, safety, tooling, policy, tutorial, other.

Prioritise technical depth over breadth.  If the content is thin or promotional, say so
concisely in the summary rather than padding it out.
"""


class DigestItem(BaseModel):
    title: str = Field(description="Punchy, specific headline — not a copy of the original")
    summary: str = Field(description="2-3 sentences; technically precise, no fluff")
    category: str = Field(
        description="One word: research | product | infrastructure | safety | tooling | policy | tutorial | other"
    )


class DigestAgent(BaseAgent):
    """Generates a DigestItem from a single article or video transcript."""

    def generate(
        self,
        article_title: str,
        content: str,
        source_type: str,
    ) -> DigestItem:
        """
        Args:
            article_title: The original article or video title.
            content:       Full transcript text or markdown body.
            source_type:   "youtube" | "openai" | "anthropic"

        Returns:
            DigestItem with title, summary, and category.
        """
        truncated = False
        if len(content) > MAX_CONTENT_CHARS:
            content = content[:MAX_CONTENT_CHARS]
            truncated = True
            logger.debug(
                "Content truncated to %d chars for '%s'", MAX_CONTENT_CHARS, article_title
            )

        user_input = (
            f"SOURCE TYPE: {source_type}\n"
            f"ORIGINAL TITLE: {article_title}\n"
            f"{'[Note: content was truncated to fit context window]' if truncated else ''}"
            f"\n\nCONTENT:\n{content}"
        )

        return self._parse(_SYSTEM_PROMPT, user_input, DigestItem)
