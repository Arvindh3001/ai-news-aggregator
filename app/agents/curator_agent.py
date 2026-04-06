"""
CuratorAgent — ranks a list of digest candidates against a user profile.

Input:  list of CandidateDigest objects + a UserProfile
Output: CuratedList where every candidate gets a relevance score (0.0–1.0)
        and a one-sentence reasoning string.

The agent returns a score for *every* candidate supplied; the caller decides
how many to keep (e.g. top-10 by score).

UserProfile loading
-------------------
`load_user_profile(path)` reads `profiles/user_profile.json` and returns a
`UserProfile` instance.  The pipeline calls this once and passes the object to
`CuratorAgent.curate()`.
"""
import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

_SYSTEM_TEMPLATE = """\
You are a personalised news curator for {name}.

User profile:
- Role / background: {background}
- Primary interests: {interests}
- Preferred depth: {preferred_depth}

Your task: score each digest item by how relevant and valuable it is to this specific reader.

Scoring rules:
- 1.0 = directly addresses a core interest with high technical depth
- 0.7–0.9 = closely related to interests, or high quality but slightly off-focus
- 0.4–0.6 = tangentially relevant or interesting but not a priority
- 0.1–0.3 = low relevance — general news, unrelated domain, or marketing-heavy
- 0.0 = completely off-topic or duplicate of a better item

For each item provide:
  - `digest_id`: the integer ID exactly as given in the input
  - `score`: a float between 0.0 and 1.0
  - `reasoning`: one sentence explaining the score

Return a score for EVERY item in the input list. Do not skip any.
"""


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class UserProfile(BaseModel):
    name: str = Field(description="Reader's first name")
    background: str = Field(description="Role and technical background")
    interests: list[str] = Field(description="Topics the reader cares most about")
    preferred_depth: str = Field(
        description="How technical the content should be: 'technical' or 'overview'"
    )


class CandidateDigest(BaseModel):
    """Lightweight view of a Digest row passed to the curator."""

    digest_id: int
    title: str
    summary: str
    category: str


class CuratedItem(BaseModel):
    digest_id: int = Field(description="Same ID as in the input candidate list")
    score: float = Field(ge=0.0, le=1.0, description="Relevance score 0.0–1.0")
    reasoning: str = Field(description="One sentence explaining this score")


class CuratedList(BaseModel):
    items: list[CuratedItem]


# ---------------------------------------------------------------------------
# Profile loader
# ---------------------------------------------------------------------------


def load_user_profile(path: str | Path = "profiles/user_profile.json") -> UserProfile:
    """Read and validate the user profile JSON file."""
    profile_path = Path(path)
    if not profile_path.exists():
        raise FileNotFoundError(
            f"User profile not found at '{profile_path}'. "
            "Create it by copying profiles/user_profile.json and filling in your details."
        )
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    return UserProfile.model_validate(data)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class CuratorAgent(BaseAgent):
    """Scores and ranks digest candidates for a specific user."""

    def curate(
        self,
        candidates: list[CandidateDigest],
        profile: UserProfile,
    ) -> list[CuratedItem]:
        """
        Score every candidate against the user profile.

        Args:
            candidates: Digest candidates to evaluate (typically today's unsent digests).
            profile:    The reader's interest profile.

        Returns:
            List of CuratedItems sorted by score descending.
            Always the same length as `candidates`.
        """
        if not candidates:
            return []

        instructions = _SYSTEM_TEMPLATE.format(
            name=profile.name,
            background=profile.background,
            interests=", ".join(profile.interests),
            preferred_depth=profile.preferred_depth,
        )

        # Format the candidate list as a numbered block so positions are unambiguous
        lines: list[str] = ["Digest candidates to score:\n"]
        for c in candidates:
            lines.append(
                f"[{c.digest_id}] {c.title}\n"
                f"    Category: {c.category}\n"
                f"    Summary:  {c.summary}\n"
            )
        user_input = "\n".join(lines)

        result: CuratedList = self._parse(instructions, user_input, CuratedList)

        # Sort descending by score before returning
        return sorted(result.items, key=lambda x: x.score, reverse=True)
