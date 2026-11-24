import json
import re

import config
from utils import ask_llm, save_output

LEVELS = {"low": 0, "medium": 1, "high": 2}

# (key, label, what "high" means)
FACTORS = [
    ("requirement_stability", "Requirement stability", "low = vague or expected to change; medium = mostly defined with some open points; high = well defined and fixed"),
    ("regulatory_criticality", "Regulatory criticality", "low = no specific regulations; medium = must follow data-protection or privacy laws (HIPAA, GDPR, DPDP) but needs no formal approval; high = needs formal certification, regulatory approval or audited compliance (e.g. medical-device rules)"),
    ("security_risk", "Security risk", "low = little or no personal data; medium = handles personal or patient records; high = highly sensitive data at scale, or controls critical functions where a breach is severe"),
    ("project_complexity", "Project complexity", "low = few simple features and 1-2 user roles; medium = several features and 3-4 roles; high = many interacting modules, rules or roles"),
    ("system_size", "System size", "low = a handful of requirements and a small user base; medium = moderate; high = many modules or a large user base"),
    ("legacy_dependence", "Legacy-system dependence", "low = standalone system; medium = integrates with a few existing systems; high = heavy integration with older systems"),
    ("change_frequency", "Expected frequency of change", "low = fixed, standard behaviour; medium = occasional changes; high = requirements mention frequent updates, new features, trends or feedback loops"),
    ("continuous_delivery_need", "Need for continuous delivery", "low = rare releases are fine; medium = periodic releases; high = frequent releases and updates are essential"),
    ("stakeholder_availability", "Stakeholder availability", "low = users rarely available; medium = periodic access; high = users and clients available for continuous feedback"),
    ("testing_documentation_need", "Testing and documentation need", "low = informal testing; medium = standard test plans and documents; high = formal test evidence, traceability and audit documentation mandated"),
    ("formal_verification_need", "Need for formal verification", "low = informal checks; medium = reviews and structured testing; high = every requirement must be formally verified and validated (safety-critical or certified systems)"),
    ("failure_consequence", "Consequence of system failure", "low = only an inconvenience; medium = disrupts services or loses data but does not directly injure anyone; high = failure can injure or kill a patient or cause severe loss"),
    ("technical_uncertainty", "Technical uncertainty", "low = standard, proven technology; medium = some new components; high = new or unproven technology, unclear feasibility"),
]
KEYS = [f[0] for f in FACTORS]

# Ideal (level, weight) per factor for each SDLC model. Level: 0 low, 1 medium, 2 high.
PROFILES = {
    "Waterfall":              [(2,2),(1,1),(1,1),(1,1),(1,1),(1,1),(0,2),(0,1),(0,1),(2,1),(0,1),(1,1),(0,2)],
    "V-Model":                [(2,2),(2,1),(2,1),(1,1),(1,1),(1,1),(0,1),(0,1),(0,1),(2,2),(2,2),(2,2),(0,1)],
    "Spiral":                 [(1,1),(1,1),(2,1),(2,2),(2,1),(1,1),(1,1),(0,1),(1,1),(1,1),(0,1),(2,1),(2,3)],
    "Agile":                  [(0,2),(0,1),(0,1),(1,1),(1,1),(0,1),(2,2),(1,1),(2,2),(0,1),(0,1),(0,1),(1,1)],
    "DevSecOps":              [(1,1),(1,1),(2,2),(1,1),(1,1),(1,1),(2,1),(2,2),(1,1),(1,1),(0,1),(1,1),(0,1)],
    "Agile-V-Model Hybrid":   [(1,2),(2,2),(1,1),(1,1),(1,1),(1,1),(1,2),(1,1),(1,1),(2,1),(1,1),(2,1),(1,1)],
    "Agile-DevSecOps Hybrid": [(1,2),(1,1),(2,2),(1,1),(1,1),(1,1),(2,2),(2,2),(1,1),(1,1),(0,1),(1,1),(1,1)],
}

# ---------------- Step 2a: derive characteristics (JSON) ----------------
ANALYSIS_SYSTEM = """You are a software engineering analyst.
You rate project characteristics using only evidence found in the requirements text."""

ANALYSIS_TEMPLATE = """Software requirements (ID: statement):

%%REQ%%

TASK: Rate each characteristic below as "low", "medium" or "high" using ONLY evidence in the requirements.
Give a very short evidence phrase (max 8 words) for each, citing requirement IDs where possible.
Do not recommend an SDLC.

For each characteristic, compare THIS project with the low / medium / high descriptions and pick the
best match (project domain: %%DOMAIN%%). Different projects must get different ratings. Being in this domain
does not by itself make a characteristic "high". Use "medium" only if the project truly sits in between.

Characteristics and their scales:
%%FACTORS%%

Reply with ONLY a JSON object, one entry per characteristic key, like this:
{"requirement_stability": {"rating": "medium", "evidence": "short phrase"}}
"""

# ---------------- Step 2b: justification ----------------
JUST_SYSTEM = """You are a software engineering consultant who explains SDLC model choices.
The ranking has already been computed by a rule-based scoring engine. You must NOT change it.
Explain it using the project characteristics and the requirements. Be concise and output only the requested format."""

JUST_TEMPLATE = """Requirements (ID: statement):
{requirements}

Key project characteristics:
{characteristics}

Ranked SDLC recommendations (computed):
{ranking}

TASK: Explain the ranking in at most 120 words in total. Use exactly this format:

## Justification for {top}
2-3 sentences linking the choice to specific characteristics and citing requirement IDs (like FR-APT-001).

## Why the Other Top Models Rank Lower
1-2 sentences on why the second and third ranked models score lower.

## Risks and Mitigation
2 short bullets: a risk of {top} for this project and how to reduce it.
"""


def _clean(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ").strip()


def compact_reqs(text: str) -> str:
    """Reduce full requirement blocks to 'ID: statement' lines (about 80% fewer tokens)."""
    def field(lines, name):
        for l in lines:
            if name in l:
                return l.split(":**", 1)[-1].strip()
        return ""

    out = []
    for block in text.split("### ")[1:]:
        lines = block.strip().splitlines()
        rid = lines[0].strip()
        stmt = field(lines, "Requirement statement")
        if not stmt:
            continue
        # keep the short fields that carry evidence for regulation / security / risk
        extras = []
        for label, name in (("Category", "Category"), ("Regulations", "Applicable regulations"),
                            ("Risk", "Risk level"), ("Priority", "Priority")):
            val = field(lines, name)
            if val:
                extras.append(f"{label}: {val}")
        out.append(f"{rid}: {stmt} [{'; '.join(extras)}]" if extras else f"{rid}: {stmt}")
    return "\n".join(out) if out else text[:2500]   # fallback if format was unexpected


def parse_analysis(raw: str) -> dict:
    data = {}
    try:
        data = json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            try:
                data = json.loads(match.group(0))
            except Exception:
                data = {}
    if not isinstance(data, dict):
        data = {}

    ratings = {}
    for key, _, _ in FACTORS:
        item = data.get(key, {})
        if not isinstance(item, dict):
            item = {}
        rating = str(item.get("rating", "medium")).lower().strip()
        if rating not in LEVELS:
            rating = "medium"
        evidence = _clean(item.get("evidence", "")) or "No evidence returned (defaulted to medium)."
        ratings[key] = {"rating": rating, "evidence": evidence}
    return ratings


def score_models(ratings: dict):
    scored = []
    for name, profile in PROFILES.items():
        total, weight_sum = 0.0, 0
        for key, (preferred, weight) in zip(KEYS, profile):
            level = LEVELS[ratings[key]["rating"]]
            total += weight * (1 - abs(level - preferred) / 2)
            weight_sum += weight
        scored.append((name, round(100 * total / weight_sum)))
    scored.sort(key=lambda item: -item[1])
    return scored


def characteristics_table(ratings: dict) -> str:
    lines = ["| Characteristic | Rating | Evidence |", "|---|---|---|"]
    for key, label, _ in FACTORS:
        r = ratings[key]
        lines.append(f"| {label} | {r['rating'].capitalize()} | {r['evidence']} |")
    return "\n".join(lines)


def ranking_table(ranking) -> str:
    lines = ["| Rank | SDLC model | Suitability score |", "|---|---|---|"]
    for i, (name, score) in enumerate(ranking, start=1):
        lines.append(f"| {i} | {name} | {score}% |")
    return "\n".join(lines)


def short_characteristics(ratings: dict) -> str:
    """Compact one-line-per-factor summary for the justification prompt (no evidence text)."""
    return "\n".join(f"- {label}: {ratings[key]['rating']}" for key, label, _ in FACTORS)


def choose_sdlc(requirements: str) -> str:
    compact = compact_reqs(requirements)

    # Step 2a: LLM rates the characteristics
    print(f"[Stage 2a] Deriving project characteristics using {config.MODEL} ...")
    factor_text = "\n".join(f"- {key}: {desc}" for key, _, desc in FACTORS)
    prompt = (ANALYSIS_TEMPLATE.replace("%%REQ%%", compact)
              .replace("%%FACTORS%%", factor_text)
              .replace("%%DOMAIN%%", config.DOMAIN))
    raw = ask_llm(ANALYSIS_SYSTEM, prompt, json_mode=True, max_tokens=config.STAGE2A_MAX_TOKENS)
    ratings = parse_analysis(raw)
    print("[Stage 2a] Ratings: " + ", ".join(f"{k}={v['rating']}" for k, v in ratings.items()))

    # Rule-based scoring (no LLM)
    ranking = score_models(ratings)
    top, top_score = ranking[0]
    chars_md = characteristics_table(ratings)
    rank_md = ranking_table(ranking)
    print(f"[Stage 2] Rule-based ranking computed. Top model: {top} ({top_score}%)")

    # Step 2b: LLM explains the ranking
    print("[Stage 2b] Writing justification ...")
    justification = ask_llm(
        JUST_SYSTEM,
        JUST_TEMPLATE.format(
            requirements=compact,
            characteristics=short_characteristics(ratings),
            ranking=rank_md,
            top=top,
        ),
        max_tokens=config.STAGE2B_MAX_TOKENS,
    )

    full = f"""Recommended SDLC: {top} (suitability score {top_score}%)

## Ranked SDLC Recommendations
{rank_md}

*Scores are computed by a rule-based multi-criteria engine from the characteristics below. They are suitability scores, not probabilities.*

## Project Characteristics (derived from the requirements)
{chars_md}

{justification}

## Human Approval Required
- **Status:** Pending human approval
- **Approvers:** Project Manager, Software Architect, Security Team, Compliance Officer
- The AI recommendation is advisory. The final SDLC choice must be approved by the people above.
"""
    path = save_output("stage2_sdlc", full)
    print(f"[Stage 2] Saved to {path}")
    return full


if __name__ == "__main__":
    import sys
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        choose_sdlc(f.read())