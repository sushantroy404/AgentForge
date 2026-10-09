# AgentForge

Privacy-first meta-agent platform. A business user chats with **The Architect**, which builds a
**Specialist** manifest through small validated patches. The backend compiles it, smoke-tests it,
and the Specialist then answers with local RAG, a controlled tool registry and code-enforced guardrails.
Everything runs locally (FastAPI + React + Ollama + LanceDB).

Implements `AgentForge MVP Blueprint v2`. Backend steps 1-11 and frontend steps 12-14 are built;
step 0 (spike) and threshold calibration are scripts you run on your machine.

## Quick start without Ollama (replay mode)

```bash
cp .env.replay.example .env
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000               # terminal 1
cd ../frontend && npm install && npm run dev   # terminal 2 -> http://localhost:5173
```

Follow `data/demo/demo_walkthrough.md` (the UI has the script as buttons). Replay mode uses a scripted
Architect, an extractive Specialist and a hash embedder, so the whole flow works with no model.

## Real mode (Ollama + Gemma)

1. `ollama serve`, then `ollama list` and pick real tags. `cp .env.example .env` and set
   `ARCHITECT_MODEL` / `SPECIALIST_MODEL` (defaults are `gemma4:e4b`; verify before trusting) and
   `ollama pull nomic-embed-text`.
2. **Step 0 gate:** `python scripts/spike_ollama.py` must print GO (tags, envelope validity,
   `num_ctx` not truncating, tool_call envelope, embeddings).
3. **Calibrate:** `python scripts/calibrate_threshold.py`, then copy `RAG_SCORE_THRESHOLD`,
   `SCOPE_OUT_MIN` and `SCOPE_MARGIN` into `.env`. The shipped values are placeholders.
4. Run backend and frontend as above. `DEMO_MODE=auto` falls back to replay if Ollama dies mid-demo.

## Tests

```bash
cd backend && pytest -q          # 58 tests, FakeLLM, no Ollama needed
pytest -q -m live                # optional: needs Ollama + the configured model
```

## Layout

See section 2 of the blueprint. `backend/app/services/specialist_runtime.py` is the 8-stage pipeline,
`guardrails.py` and `scope_gate.py` hold the code-enforced safety, `compiler_service.py` builds the
assertion-based smoke suite, `frontend/src/components` has the two workspaces.

## Differences from the blueprint (deliberate)

- Patch ops are validated **per op** in `spec_manager` (a bad op is rejected and fed back to the Architect)
  instead of a Pydantic validator on `PatchOp`, which would void the whole turn.
- Chunking splits on headings first and windows (500/100) only long sections.
- No `specialist_answers.json`: replay answers come from heuristics in `demo_replay.py`.
- `think` is not sent to Ollama; if Gemma's thinking mode breaks `format`, disable it per your Ollama version.
- Rejected ops carry their `value` so the Architect can see what it tried.

## Known limits

- **Not run against real Gemma/Ollama** (none was available where this was built). The spike, the live
  test and calibration exist for exactly that. Expect to tune prompts and thresholds.
- Jobs are in-memory (lost on restart); sessions and manifests persist to `data/manifests`.
- In `DEMO_MODE=auto`, embeddings fall back to the hash embedder only if Ollama is down; do not mix
  collections built under different embedders.
- Replay-mode thresholds (`.env.replay.example`) suit the hash embedder, not nomic-embed-text.
