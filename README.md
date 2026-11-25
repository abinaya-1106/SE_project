# Requirements and SDLC Recommendation Generator

A local, LLM-assisted tool that takes a functionality description (for example, *"online appointment
booking for patients and doctors"*), generates structured software requirements for it, and then
recommends and ranks suitable SDLC models with an explanation. Everything runs on your own machine
through [Ollama](https://ollama.com), so no data leaves the computer.

The AI output is **advisory**. Every result is marked *Pending human approval*.

---

## How it works

```
functionality
   |
   v
Stage 1   LLM writes 4 functional + 3 non-functional requirements (one requirement per call)
   |
   v
Stage 2a  LLM rates 13 project characteristics (low / medium / high) as JSON
   |
   v
Scoring   Python formula ranks 7 SDLC models and gives suitability percentages (no LLM)
   |
   v
Stage 2b  LLM writes a short justification of the computed ranking
   |
   v
Human approval (Accept / Reject / Regenerate in the web UI)
```

The LLM never chooses the SDLC. It writes text and rates characteristics. The ranking is calculated
by a fixed, repeatable formula, which follows the hybrid design in the problem statement
(deterministic rules + multi-criteria analysis + LLM-generated explanations).

### How the ranking is calculated

Each SDLC model (Waterfall, V-Model, Spiral, Agile, DevSecOps, Agile-V-Model Hybrid,
Agile-DevSecOps Hybrid) has a profile in `src/stage2_sdlc.py`: for each of the 13 characteristics, the
level it prefers (0 = low, 1 = medium, 2 = high) and a weight for how much that factor matters.

For every model and factor:

```
match = 1 - |rated level - preferred level| / 2        # 1.0 exact, 0.5 one level off, 0 two levels off
score = 100 x sum(weight x match) / sum(weights)
```

Models are sorted by score, highest first. The scores are **suitability scores, not probabilities**.
The profile weights are hand-set design assumptions, not measured data.

Evidence guard (calibration rule): *regulatory criticality*, *formal verification need* and *failure
consequence* can only stay "high" if the project text contains explicit evidence (patient-safety,
medical-device or certification terms). Otherwise they are capped at "medium". This stops a small
model from over-rating every healthcare project.

---

## Project structure

```
se_llm_project/
  app.py                  Flask web server (routes /stage1 and /stage2)
  run_all.py              Run the whole pipeline from the terminal
  make_report.py          Builds a combined report (called by run_all.py)
  README.md
  data/
    healthcare/           Reference documents (.txt / .pdf) fed to Stage 1
      01_appointment_booking_requirements.txt
      02_hipaa_security_and_privacy_requirements.txt
      03_india_abdm_and_dpdp_requirements.txt
      04_quality_and_operational_requirements.txt
      SOURCES.md          Provenance of the data (ignored by the loader)
  src/
    config.py             All settings
    utils.py              Document loading, Ollama calls, saving output
    stage1_requirements.py   Requirement generation
    stage2_sdlc.py        Characteristic rating, scoring, justification
  templates/
    index.html            Web page
  outputs/                Generated results (timestamped .md files)
```

### What each file does

| File | Purpose |
|---|---|
| `src/config.py` | Model name, domain, default functionality, Ollama URL, speed settings, token limits, number of requirements |
| `src/utils.py` | `load_documents()` reads `data/<domain>/`, `ask_llm()` calls Ollama, `warm_up()` preloads the model, `save_output()` writes results |
| `src/stage1_requirements.py` | Plans 4 functional capabilities, then generates each requirement in its own call with 8 fields; parses and formats the results |
| `src/stage2_sdlc.py` | Defines the 13 factors and 7 SDLC profiles, asks the LLM to rate the factors, applies the evidence guard, scores and ranks, then asks the LLM for a justification |
| `app.py` | Web server: `/stage1` generates requirements, `/stage2` recommends an SDLC |
| `templates/index.html` | Input box, progress, results, and the approval buttons |
| `run_all.py` | Terminal version; prints per-stage timings |

---

## Setup

1. **Install Ollama** and pull the model:
   ```bash
   ollama pull qwen3:1.7b
   ```
2. **Create a virtual environment and install packages** (Python 3.9+):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install flask markdown pypdf httpx
   ```
3. **Add reference data** as `.txt` or `.pdf` files in `data/healthcare/`. The folder name must match
   `DOMAIN` in `src/config.py`.

## Run

Web interface:
```bash
python app.py
```
Open http://127.0.0.1:5000, enter a functionality, and click Run. Restart `app.py` after editing any
code, because the server does not reload automatically.

Terminal:
```bash
python run_all.py "fitness and wellness tracking mobile app"
```
Results are saved in `outputs/` as `stage1_requirements_<time>.md` and `stage2_sdlc_<time>.md`.

---

## Output

**Stage 1** gives 4 functional (`FR-xxx-001..004`) and 3 non-functional (`NFR-xxx-001..003`)
requirements. Each has: requirement statement, category, source stakeholder, priority, acceptance
criteria, applicable regulations, risk level, confidence score and approval status.

**Stage 2** gives the recommended SDLC with its score, the ranked table of all seven models, the table
of 13 characteristics with ratings and evidence, a short justification (why this model, why the others
rank lower, risks and mitigation), and the human-approval section.

Example expectations (assuming sensible ratings): an infusion-pump control system should rank
V-Model first, a fitness app should favour Agile or DevSecOps-style models, and appointment booking
usually gives a close Waterfall / V-Model result.

---

## Settings (`src/config.py`)

| Setting | Meaning |
|---|---|
| `MODEL` | Ollama model name (for example `qwen3:1.7b`, `qwen3:4b`) |
| `DOMAIN` | Folder inside `data/` to read |
| `MAX_DOC_CHARS` | Total characters of reference data sent to the model, split evenly across files; only the start of each file is used |
| `TEMPERATURE` | 0.2-0.4 works well for Qwen3 (values near 0 can cause early stops and repetition) |
| `NUM_CTX` | Context window; smaller is faster |
| `KEEP_ALIVE` | How long the model stays loaded in memory |
| `NUM_FR`, `NUM_NFR` | How many functional / non-functional requirements to generate |
| `REQ_CODE` | Three-letter ID code (for example `APT`); empty means automatic |
| `STAGE1_BLOCK_TOKENS`, `STAGE2A_MAX_TOKENS`, `STAGE2B_MAX_TOKENS` | Reply length limits per call |

Speed tips: the target is about 2-2.5 minutes per run. Check that Ollama uses the GPU (`ollama ps`),
keep `MAX_DOC_CHARS` modest, and keep the most important content at the top of each data file.

---

## Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| `Folder not found: data/healthcare` | Run from the project folder and make sure `data/<DOMAIN>/` exists |
| Same result after editing code | The web server is still running old code: stop `app.py` and start it again |
| Only one requirement appears | An old `stage1_requirements.py` is in use; the log should show `v3 (one block per call)` |
| Every project ranks the same SDLC | Check the `[Stage 2a] Ratings:` line in the terminal; if ratings barely vary, the small model is the limit, so try `qwen3:4b` for Stage 2a |
| Error mentioning `think` | Your Ollama is too old: update it, or remove the `"think": False` line in `utils.py` |
| Slow runs | Model running on CPU, or too much reference text; see the speed tips above |

---

## Limitations

- A small local model (1.7B) is weaker at judgement than large cloud models; the formula and guard
  rules exist to reduce that dependence.
- SDLC profile weights are hand-set assumptions.
- Scores are suitability scores, not probabilities.
- The reference data are paraphrased summaries of public sources, not real project documents (see
  `data/healthcare/SOURCES.md`). Verify regulatory details against the official sources before citing.
- Outputs are advisory and must be approved by the Project Manager, Software Architect, Security Team
  and Compliance Officer.