import re

import config
from utils import load_documents, ask_llm, save_output

SYSTEM_PROMPT = """You are a senior software requirements engineer working on healthcare software.
You are given informal requirement descriptions from past projects.
Learn the typical needs and constraints from them, then write structured, testable
requirements for the new functionality requested. Do not invent unrelated features.
Only name a regulation if it clearly applies to this functionality (for example HIPAA or GDPR for
personal health data, or India's DPDP Act 2023) or is mentioned in the references. Do not mention
medical-device standards unless the functionality is a medical device. If unsure, write "None identified"
and lower the confidence score.
Be concise: every field is one short line. Output only the requested format, nothing else."""

FIELD_NAMES = ["Requirement statement", "Category", "Source stakeholder", "Priority",
               "Acceptance criteria", "Applicable regulations", "Risk level", "Confidence score"]

FIELDS = """- **Requirement statement:** The system shall ... (max 20 words)
- **Category:** one or two of: Business, Functional, Security, Privacy, Regulatory, Performance, Availability and Reliability, Usability, Data-management, Integration, Audit and Reporting
- **Source stakeholder:** who needs this (e.g. Doctor, Patient, Administrator)
- **Priority:** High / Medium / Low
- **Acceptance criteria:** one testable, measurable condition (max 20 words)
- **Applicable regulations:** regulation names, or None identified
- **Risk level:** High / Medium / Low
- **Confidence score:** 0-100%"""

# The shared prefix is identical in every call, so Ollama reuses its cached prompt processing.
CONTEXT_TEMPLATE = """Existing requirement descriptions from the {domain} domain:

{docs}

-----
Functionality to specify: "{functionality}"
"""

BLOCK_INSTRUCTIONS = """Write ONE requirement using EXACTLY these fields, one short line each.
Output only the 8 field lines: no heading, no intro, no extra text.

{fields}
"""

PLAN_INSTRUCTIONS = """List exactly {n} distinct core functional capabilities this system needs,
one per line, 3-8 words each. Output only the numbered list."""

NFR_TOPICS = ["security", "privacy", "performance", "availability", "usability", "auditability"]
APPROVAL_LINE = "- **Approval status:** Pending human approval"
CODE_STOPWORDS = {"online", "the", "a", "an", "for", "and", "of", "to", "with", "system", "new"}

_BOLD_RE = re.compile(r"\*\*\s*([^*\n]+?)\s*:?\s*\*\*\s*:?\s*(.*)")
_PLAIN_RE = re.compile(r"^\s*[-*]?\s*([A-Za-z ]+?)\s*:\s*(.+)$")


def make_code(functionality: str) -> str:
    if config.REQ_CODE:
        return config.REQ_CODE.upper()
    words = [w for w in re.findall(r"[A-Za-z]+", functionality) if w.lower() not in CODE_STOPWORDS]
    return (words[0][:3] if words else "REQ").upper()


def nfr_focuses(n: int):
    """Split the six quality topics across n non-functional requirements."""
    k = -(-len(NFR_TOPICS) // n)
    chunks = [NFR_TOPICS[i * k:(i + 1) * k] for i in range(n)]
    return [("a non-functional requirement covering " + " and ".join(c)) if c
            else "another important quality attribute for this system" for c in chunks]


def parse_fields(text: str) -> dict:
    """Tolerantly pull the 8 fields out of the model's reply (bold or plain, any order)."""
    found = {}
    for line in text.splitlines():
        m = _BOLD_RE.search(line) or _PLAIN_RE.match(line)
        if not m:
            continue
        name = m.group(1).strip().rstrip(":").lower()
        for f in FIELD_NAMES:
            if name == f.lower() and f not in found and m.group(2).strip():
                found[f] = m.group(2).strip()
    return found


def format_block(rid: str, found: dict) -> str:
    defaults = {"Applicable regulations": "None identified",
                "Requirement statement": "Not generated - please re-run"}
    lines = [f"### {rid}"]
    for f in FIELD_NAMES:
        lines.append(f"- **{f}:** {found.get(f) or defaults.get(f, 'Not specified')}")
    lines.append(APPROVAL_LINE)
    return "\n".join(lines)


def plan_functions(context: str, n: int):
    """One tiny call: the model lists n distinct functional capabilities."""
    out = ask_llm(SYSTEM_PROMPT, context + "\n" + PLAN_INSTRUCTIONS.format(n=n),
                  max_tokens=config.STAGE1_PLAN_TOKENS)
    items = []
    for line in out.splitlines():
        line = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "", line).replace("**", "").strip()
        if line and not line.endswith(":"):
            items.append(line)
    items = items[:n]
    return items + [None] * (n - len(items))


def generate_block(context: str, rid: str, focus: str, prior: str):
    fixed = BLOCK_INSTRUCTIONS.format(fields=FIELDS)
    prompt = (context + "\n" + fixed +
              f"\nRequirement ID: {rid}\nFocus: {focus}\n"
              f"Already written (do not repeat these):\n{prior or '(none yet)'}\n")
    found = {}
    for _ in range(2):
        out = ask_llm(SYSTEM_PROMPT, prompt, max_tokens=config.STAGE1_BLOCK_TOKENS,
                      stop=["\n###", "\n##"])
        found = parse_fields(out)
        if "Requirement statement" in found and len(found) >= 6:
            break
        print(f"    [!] {rid}: incomplete output, retrying ...")
    return format_block(rid, found), found.get("Requirement statement", "")


def generate_requirements(functionality: str = None) -> str:
    functionality = functionality or config.FUNCTIONALITY
    config.FUNCTIONALITY = functionality   # Stage 2 reads this
    docs = load_documents(config.DOMAIN)
    context = CONTEXT_TEMPLATE.format(domain=config.DOMAIN, docs=docs, functionality=functionality)
    code = make_code(functionality)

    print(f"[Stage 1] v3 (one block per call) - generating requirements using {config.MODEL} ...")
    fr_items = plan_functions(context, config.NUM_FR)
    jobs = [(f"FR-{code}-{i + 1:03d}",
             f"functional capability: {item}" if item else "a core functional capability not yet covered")
            for i, item in enumerate(fr_items)]
    jobs += [(f"NFR-{code}-{i + 1:03d}", focus) for i, focus in enumerate(nfr_focuses(config.NUM_NFR))]

    frs, nfrs, prior = [], [], ""
    for rid, focus in jobs:
        print(f"[Stage 1] {rid} ...")
        block, statement = generate_block(context, rid, focus, prior)
        (nfrs if rid.startswith("NFR-") else frs).append(block)
        prior += f"- {rid}: {statement}\n"

    final = ("## 1. Functional Requirements\n\n" + "\n\n".join(frs) +
             "\n\n## 2. Non-Functional Requirements\n\n" + "\n\n".join(nfrs) + "\n")
    path = save_output("stage1_requirements", final)
    print(f"[Stage 1] Saved to {path} ({len(frs)} FR, {len(nfrs)} NFR)")
    return final


if __name__ == "__main__":
    generate_requirements()