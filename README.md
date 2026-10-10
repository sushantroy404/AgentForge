# AgentForge

Privacy-first meta-agent platform. You chat with **The Architect**, which builds a **Specialist**
definition through small validated patches. The backend compiles it, smoke-tests it, and the
Specialist then answers using local RAG over your documents, a controlled tool registry and
code-enforced guardrails. Everything runs locally: FastAPI + React + Ollama + LanceDB.

There is no demo mode, no scripted answers and no sample data in the product. Every answer comes
from the real model; you describe the Specialist to the Architect yourself and upload your own document.

## Setup

1. Install Python 3.11+, Node 20+ and [Ollama](https://ollama.com). Run `ollama serve`.
2. `ollama list`, choose chat model tags, then `ollama pull nomic-embed-text`.
3. `cp .env.example .env` and set `ARCHITECT_MODEL` / `SPECIALIST_MODEL` to tags you actually have.
4. **Go/no-go check:** `python scripts/spike_ollama.py` must print GO.
5. **Calibrate thresholds** on your own document and questions (see the script's docstring):
   `python scripts/calibrate_threshold.py doc.md --in-queries in.txt --out-queries out.txt --in-topics in_topics.txt --out-topics out_topics.txt`
   then copy `RAG_SCORE_THRESHOLD`, `SCOPE_OUT_MIN`, `SCOPE_MARGIN` into `.env`. Shipped values are placeholders.

```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
uvicorn app.main:app --port 8000                 # terminal 1
cd frontend && npm install && npm run dev         # terminal 2 -> http://localhost:5173
```

If Ollama is not running the app returns a clear 503 and the header shows "Start Ollama".

## Using it

1. Open the **Build** tab and describe your Specialist to the Architect in your own words.
2. Upload a reference document (PDF, MD or TXT).
3. Click **Build Specialist** (or **Fill defaults and build**; defaults are listed as assumptions).
4. Open the **Try a Specialist** tab and chat with it. The sidebar shows safety checks, retrieved
   sources, tool calls and which gate fired.

## Tools

The registry (`backend/app/tools/registry.py`) ships with **no tools**, so the Architect will not
propose any. Add real ones with `@register_tool(...)` and import the module in `app/main.py`.

## Tests

```bash
cd backend && pytest -q     # uses a test-only fake LLM and fixtures under backend/tests; no Ollama needed
pytest -q -m live           # optional, needs Ollama
```

`backend/tests/` holds the only scripted LLM, sample documents and sample tools. None of it is
imported by the app.

## Known limits

- Not yet run against a real Gemma/Ollama install in the environment this was built in; the spike,
  the live test and calibration exist for that.
- Jobs are in memory (lost on restart); sessions and manifests persist to `data/manifests`.
