"""
EmailService — builds the HTML email and delivers it via Gmail SMTP.

HTML assembly is done here (not by the AI agent) so the layout is always
consistent and never garbled by model output.  The agent-generated prose
(subject, greeting, sign_off) is injected into a fixed template.

Gmail SMTP:
  Host:  smtp.gmail.com
  Port:  587 (STARTTLS)
  Auth:  MY_EMAIL + MY_EMAIL_APP_PASSWORD (Gmail App Password, not account password)
"""
import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.agents.email_agent import EmailContent
from app.database.connection import settings

logger = logging.getLogger(__name__)

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587

# ---------------------------------------------------------------------------
# Data transfer object — one entry in the email article list
# ---------------------------------------------------------------------------


@dataclass
class EmailArticle:
    title: str
    summary: str
    category: str
    source_url: str
    score: float
    article_type: str   # youtube | openai | anthropic


# ---------------------------------------------------------------------------
# HTML template helpers
# ---------------------------------------------------------------------------

_CATEGORY_COLORS: dict[str, str] = {
    "research":       "#6366f1",
    "product":        "#0ea5e9",
    "infrastructure": "#f59e0b",
    "safety":         "#ef4444",
    "tooling":        "#10b981",
    "policy":         "#8b5cf6",
    "tutorial":       "#f97316",
    "other":          "#6b7280",
}

_SOURCE_LABELS: dict[str, str] = {
    "youtube":    "YouTube",
    "openai":     "OpenAI",
    "anthropic":  "Anthropic",
}


def _category_badge(category: str) -> str:
    color = _CATEGORY_COLORS.get(category.lower(), _CATEGORY_COLORS["other"])
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:11px;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:0.5px;">'
        f"{category}</span>"
    )


def _article_card(idx: int, article: EmailArticle) -> str:
    badge = _category_badge(article.category)
    source_label = _SOURCE_LABELS.get(article.article_type, article.article_type.capitalize())
    return f"""
    <tr>
      <td style="padding:0 0 24px 0;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background:#ffffff;border:1px solid #e5e7eb;
                      border-radius:8px;overflow:hidden;">
          <tr>
            <td style="padding:20px 24px 16px 24px;">
              <p style="margin:0 0 8px 0;font-size:12px;color:#9ca3af;">
                #{idx} &nbsp;·&nbsp; {source_label} &nbsp;·&nbsp; {badge}
              </p>
              <h2 style="margin:0 0 10px 0;font-size:17px;font-weight:700;
                         color:#111827;line-height:1.4;">
                {article.title}
              </h2>
              <p style="margin:0 0 16px 0;font-size:14px;color:#374151;line-height:1.6;">
                {article.summary}
              </p>
              <a href="{article.source_url}"
                 style="display:inline-block;font-size:13px;font-weight:600;
                        color:#6366f1;text-decoration:none;">
                Read more &rarr;
              </a>
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def build_html(
    content: EmailContent,
    articles: list[EmailArticle],
    reader_name: str,
) -> str:
    """Assemble the full HTML email from agent-generated text + article cards."""
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    cards = "\n".join(_article_card(i + 1, a) for i, a in enumerate(articles))
    greeting_html = content.greeting.replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{content.subject}</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,
             BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:#f3f4f6;padding:32px 16px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" border="0"
               style="max-width:600px;width:100%;">

          <!-- Header -->
          <tr>
            <td style="padding:0 0 24px 0;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:#111827;border-radius:8px;padding:24px;">
                <tr>
                  <td>
                    <p style="margin:0 0 4px 0;font-size:11px;font-weight:600;
                               color:#6366f1;text-transform:uppercase;letter-spacing:1px;">
                      AI News Digest
                    </p>
                    <h1 style="margin:0 0 4px 0;font-size:22px;font-weight:800;
                                color:#ffffff;line-height:1.3;">
                      {content.subject}
                    </h1>
                    <p style="margin:0;font-size:13px;color:#9ca3af;">{today}</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Greeting -->
          <tr>
            <td style="padding:0 0 24px 0;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:#ffffff;border:1px solid #e5e7eb;
                            border-radius:8px;padding:24px;">
                <tr>
                  <td style="font-size:15px;color:#374151;line-height:1.7;">
                    {greeting_html}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Article cards -->
          {cards}

          <!-- Sign-off -->
          <tr>
            <td style="padding:0 0 32px 0;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:#ffffff;border:1px solid #e5e7eb;
                            border-radius:8px;padding:20px 24px;">
                <tr>
                  <td style="font-size:14px;color:#6b7280;line-height:1.6;">
                    {content.sign_off}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="text-align:center;padding:0 0 16px 0;">
              <p style="margin:0;font-size:12px;color:#9ca3af;">
                AI News Aggregator &nbsp;·&nbsp; Sent to {reader_name}
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EmailService:
    """Sends the daily digest HTML email via Gmail SMTP (STARTTLS, port 587)."""

    def __init__(self) -> None:
        self._sender = settings.MY_EMAIL
        self._password = settings.MY_EMAIL_APP_PASSWORD

    def send_digest(
        self,
        content: EmailContent,
        articles: list[EmailArticle],
        reader_name: str,
    ) -> None:
        """
        Build the HTML email and send it.

        Args:
            content:     AI-generated subject, greeting, sign_off.
            articles:    Ordered list of EmailArticle objects (top-N, score-ranked).
            reader_name: Reader's first name (used in footer).

        Raises:
            smtplib.SMTPException: on connection or auth failure (not caught here —
                                   the pipeline decides whether to retry or abort).
        """
        if not self._sender or not self._password:
            raise ValueError(
                "MY_EMAIL and MY_EMAIL_APP_PASSWORD must be set in .env before sending."
            )

        html_body = build_html(content, articles, reader_name)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = content.subject
        msg["From"] = self._sender
        msg["To"] = self._sender
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        logger.info("Connecting to %s:%d …", _SMTP_HOST, _SMTP_PORT)
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(self._sender, self._password)
            smtp.sendmail(self._sender, self._sender, msg.as_string())

        logger.info("Email sent — subject: '%s'  articles: %d", content.subject, len(articles))
