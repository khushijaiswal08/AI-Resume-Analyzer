"""Layer 9 (guardrail half): check LLM bullet rewrites before they reach the user.

The LLM may reword one of the weakest bullets, but it must not add facts. The checks are
mechanical: the rewrite may not contain a number or a skill that the original bullet did not,
it must be about one of the bullets we sent, and it must not leak contact details. Violators
are dropped with a warning. Scores are computed before this runs and never depend on it.
"""

from resume_analyzer.llm.guard import clean, numbers_in, skills_in
from resume_analyzer.redaction import redact
from resume_analyzer.schemas import BulletItem, BulletRewrite

MAX_REWRITES = 3
WEAK_BELOW = 75  # bullets scoring under this are candidates; the lowest few are sent


def pick_weakest(items: list[BulletItem], limit: int = MAX_REWRITES) -> list[BulletItem]:
    """The lowest-scoring bullets (score < 75), lowest first, ties in resume order."""
    candidates = [item for item in items if item.score < WEAK_BELOW]
    return sorted(candidates, key=lambda item: item.score)[:limit]


def _key(text: str) -> str:
    return " ".join(text.lower().split())


def ground_rewrites(
    suggestions: list[tuple[str, str]], sent: list[BulletItem], warnings: list[str]
) -> list[BulletRewrite]:
    """Keep rewrites that add no number or skill. `suggestions` are (original, rewrite) pairs.

    `sent` are the bullets we showed the model. The model's "original" is matched to them
    ignoring case and spacing; anything else is dropped. Appends a warning per drop reason.
    """
    by_key = {_key(redact(item.text)[0]): item for item in sent}
    kept: list[BulletRewrite] = []
    dropped: dict[str, int] = {}

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for original, rewrite in suggestions:
        item = by_key.get(_key(original))
        text = clean(rewrite)
        if item is None:
            drop("not one of the bullets that were sent")
            continue
        redacted_original = redact(item.text)[0]
        if not text or len(text.split()) < 3 or _key(text) == _key(redacted_original):
            drop("empty or unchanged")
        elif redact(text)[0] != text or "[EMAIL]" in text or "[PHONE]" in text:
            drop("contained contact details")
        elif numbers_in(text) - numbers_in(redacted_original):
            drop("added numbers that are not in the original")
        elif skills_in(text) - skills_in(redacted_original):
            drop("added skills that are not in the original")
        elif all(existing.original != item.text for existing in kept):
            kept.append(
                BulletRewrite(
                    original=item.text,
                    rewrite=text,
                    score_before=item.score,
                    start=item.start,
                    end=item.end,
                )
            )
    for reason, count in dropped.items():
        warnings.append(f"Dropped {count} bullet rewrite(s): {reason}.")
    return kept[:MAX_REWRITES]
