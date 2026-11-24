# ---- Settings you can change ----
MODEL = "qwen3:1.7b"           # any model you pulled with `ollama pull`
DOMAIN = "healthcare"          # must match folder name inside data/
FUNCTIONALITY = "online appointment booking for patients and doctors"

# Ollama server (native API is used for speed options like num_ctx / keep_alive)
OLLAMA_URL = "http://localhost:11434"

# Kept only so older scripts (e.g. make_report.py) that may import them don't break
BASE_URL = "http://localhost:11434/v1"
API_KEY = "ollama"

TEMPERATURE = 0.3              # Qwen3 behaves badly near 0 (early stops, repetition); 0.2-0.4 is a good range
MAX_DOC_CHARS = 4500           # total chars of reference docs sent to the model (was 12000)
MAX_TOKENS = 1200              # default cap if a call doesn't set its own

# ---- Speed settings ----
NUM_CTX = 4096                 # context window; smaller = faster and less memory
KEEP_ALIVE = "30m"             # keep model loaded in memory between calls/runs

# ---- Stage 1: requirements are generated ONE BLOCK PER CALL ----
NUM_FR = 4                     # functional requirements
NUM_NFR = 3                    # non-functional (they are split across security, privacy,
                               # performance, availability, usability, auditability)
REQ_CODE = ""                  # 3-letter ID code, e.g. "APT" -> FR-APT-001. Empty = auto from functionality
STAGE1_BLOCK_TOKENS = 300      # cap for one requirement block
STAGE1_PLAN_TOKENS = 120       # cap for the short list of functional capabilities
STAGE1_MAX_TOKENS = 1200       # unused now, kept for compatibility

# ---- Stage 2 output caps ----
STAGE2A_MAX_TOKENS = 600
STAGE2B_MAX_TOKENS = 350