"""
EmailAgent — generates the human-facing text for the daily digest email.

The agent produces three text pieces:
  - subject:   email subject line (personalised, mentions top topic)
  - greeting:  1-2 paragraph intro that frames today's digest for the reader
  - sign_off:  brief closing sentence

The EmailService takes these text pieces and composes the full HTML around them,
inserting the article cards from its own template.  Keeping prose generation
separate from HTML assembly makes both parts easier to test and change.
"""
import logging

from pydantic import BaseModel, Field

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are writing the introductory copy for a personalised AI news digest email.

You will be given:
  - The reader's name and background
  - A numbered list of today's top articles (title, category, one-line summary)

Your job is to write three things:

1. `subject` — the email subject line.
   - Be specific: mention the single most interesting topic or announcement.
   - Keep it under 70 characters.
   - Do NOT use clickbait or emoji.
   - Example: "GPT-5 architecture details, Gemini 2.0 benchmarks, and 8 more"

2. `greeting` — a 2-3 sentence intro paragraph.
   - Address the reader by first name.
   - Briefly highlight the 1-2 most important stories and why they matter technically.
   - Tone: peer-to-peer, like a knowledgeable colleague sharing a quick summary.
   - Do NOT list all articles — that's what the email body is for.

3. `sign_off` — a single closing sentence (e.g. "Enjoy the read — see you tomorrow.").
   - Keep it short and natural. No sign-off name needed.
"""


class EmailContent(BaseModel):
    subject: str = Field(description="Email subject line, under 70 chars, no emoji")
    greeting: str = Field(description="2-3 sentence personalised intro paragraph")
    sign_off: str = Field(description="Single closing sentence")


class EmailAgent(BaseAgent):
    """Generates the personalised prose sections of the daily digest email."""

    def generate(
        self,
        reader_name: str,
        reader_background: str,
        top_articles: list[dict],
    ) -> EmailContent:
        """
        Args:
            reader_name:       First name of the reader.
            reader_background: One-line role description from user profile.
            top_articles:      List of dicts with keys: title, category, summary.
                               Pass the top-N items in score order.

        Returns:
            EmailContent with subject, greeting, and sign_off.
        """
        lines = [
            f"Reader: {reader_name}",
            f"Background: {reader_background}",
            "",
            "Today's top articles:",
        ]
        for i, article in enumerate(top_articles, start=1):
            lines.append(
                f"{i}. [{article['category'].upper()}] {article['title']}\n"
                f"   {article['summary']}"
            )

        user_input = "\n".join(lines)
        return self._parse(_SYSTEM_PROMPT, user_input, EmailContent)
