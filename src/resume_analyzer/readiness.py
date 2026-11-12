"""Layer 10: composite readiness.

One headline number that combines the other layers, shown NEXT TO the explainable v1 ATS
score, never instead of it. Each component keeps its own score and a note, and the weights are
shown, so the combination can be checked by hand:

    readiness = sum(component score * weight) / 100

Components: ATS-style score, bullet quality, parse-ability, and fit (JD match if a JD was
given, else role fit if a role was picked). Components that do not apply are left out and
their weight is shared proportionally by the rest.
"""

import math

from resume_analyzer.schemas import Readiness, ReadinessComponent

BASE_WEIGHTS = {"ats": 35, "bullets": 25, "parseability": 20, "fit": 20}
LABELS = [(85, "Strong"), (70, "Good"), (50, "Needs work"), (0, "Major gaps")]


def _weights(present: list[str]) -> dict[str, int]:
    """Integer weights for the present components that sum to exactly 100 (largest remainder)."""
    total = sum(BASE_WEIGHTS[name] for name in present)
    exact = {name: BASE_WEIGHTS[name] * 100 / total for name in present}
    weights = {name: math.floor(value) for name, value in exact.items()}
    for name in sorted(exact, key=lambda n: exact[n] - weights[n], reverse=True)[
        : 100 - sum(weights.values())
    ]:
        weights[name] += 1
    return weights


def build_readiness(
    *,
    ats_total: int,
    bullet_average: int | None,
    parse_score: int,
    fit_percent: int | None,
    fit_label: str | None,
) -> Readiness:
    """Combine the layer scores. `fit_label` names the fit source ("Job match" or "Role fit")."""
    parts: dict[str, tuple[str, int, str]] = {
        "ats": (
            "ATS-style score",
            ats_total,
            "The explainable v1 score (sections, skills, verbs...).",
        ),
        "parseability": ("Parse-ability", parse_score, "Would the text survive an ATS parser?"),
    }
    if bullet_average is not None:
        parts["bullets"] = ("Bullet quality", bullet_average, "Average score of your bullets.")
    if fit_percent is not None and fit_label:
        parts["fit"] = (fit_label, fit_percent, "How well your skills cover the target.")

    weights = _weights(list(parts))
    components = [
        ReadinessComponent(id=key, label=label, score=score, weight=weights[key], note=note)
        for key, (label, score, note) in parts.items()
    ]
    score = round(sum(c.score * c.weight for c in components) / 100)
    label = next(name for floor, name in LABELS if score >= floor)
    left_out = [name for name in BASE_WEIGHTS if name not in parts]
    explanation = (
        "Composite of " + ", ".join(c.label for c in components) + " (weights shown). "
        "It sits beside the ATS-style score and does not replace it."
    )
    if left_out:
        explanation += " Components with nothing to measure were left out and their weight shared."
    return Readiness(score=score, label=label, components=components, explanation=explanation)
