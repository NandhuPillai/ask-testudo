# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**ask-testudo** is a full-stack RAG-based question-answering system for University of Maryland academic policy. Students ask natural-language questions; the system retrieves relevant passages from official UMD PDFs and generates grounded answers with citations.

**Monorepo structure:**
- **Backend** (`query.py`, root) — FastAPI server handling live question answering. This runs in production.
- **Frontend** (`frontend/`) — Next.js 16.2.1 + React 19 chat UI that calls the backend.
- **Ingestion** (`ingest.py`, root) — One-time process that parses PDFs, creates chunks, fits BM25, embeds with Cohere, and upserts to Pinecone.
- **Evaluation** (`eval/`) — RAGAS evaluation pipeline for measuring retrieval quality.

## Platform

This project now runs on an **M5 Pro MacBook Pro** (Apple Silicon, macOS). All shell commands use Unix paths (`/bin/`, not `\Scripts\`). Windows-style paths in any older docs or comments are outdated.

## Virtual Environments

There are three separate venvs — keep them isolated, never cross-install:

| Venv | Purpose | Python | How to activate |
|---|---|---|---|
| `.venv` | Backend query server + verify script | system | `.venv/bin/activate` |
| `.venv-ingest-macos` | PDF ingestion (unstructured, hi_res) | 3.11 (conda) | use full binary path (see below) |
| `.venv-eval` | RAGAS evaluation | system | `.venv-eval/bin/activate` |

**Important:** `.venv-ingest-macos` is a conda environment. Do NOT use `conda activate` — it doesn't propagate reliably in all shell contexts. Always invoke via the full binary path:
```bash
.venv-ingest-macos/bin/python3 -u ingest.py
```

**Known conflict:** `requirements_ingestion.txt` installs `pinecone-client` (old package) which conflicts with `pinecone` (v7+). After installing from requirements into any venv, always run:
```bash
pip uninstall -y pinecone-client
pip install --force-reinstall pinecone==7.3.0
```

## Running the Query Server (Backend)

```bash
# Start the server (production port)
.venv/bin/uvicorn query:app --host 0.0.0.0 --port 8000

# Start for evaluation runs (keeps port 8000 free for production)
.venv/bin/uvicorn query:app --port 8002

# Health check
curl http://localhost:8000/health

# Warm ping (used by frontend to wake Railway cold starts)
curl http://localhost:8000/ping

# Ask a question
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the minimum GPA to graduate?"}'

# Evaluation-only endpoint (returns retrieved contexts for RAGAS)
curl -X POST http://localhost:8002/ask_with_contexts \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the CS major requirements?", "stream": false, "history": []}'
```

## Running the Frontend

```bash
cd frontend
npm install          # first time only
npm run dev          # starts on http://localhost:3000
npm run build        # production build
npm run start        # serve production build
```

The frontend expects the backend at `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`).

## Running Ingestion

Ingestion uses `.venv-ingest-macos` (Python 3.11). Always use `caffeinate` to prevent sleep and `-u` for unbuffered output (output is fully buffered when piped without `-u`, so nothing appears for minutes):

```bash
# Full corpus ingestion (~2-4 hours for 311 PDFs with hi_res)
caffeinate -i .venv-ingest-macos/bin/python3 -u ingest.py 2>&1 | tee ingest_hires.log

# Verify ingestion output is healthy
.venv/bin/python3 verify_ingestion.py
```

**First run note:** The hi_res strategy downloads detectron2 ONNX model weights (~200MB) to `~/.cache/unstructured/` on first use. Subsequent runs skip the download.

**Academic Catalog note:** `2025-2026 Academic Catalog.pdf` is processed with `ocr_only` strategy (not `hi_res`) because hi_res struggles with multi-column layouts. This is configured automatically in `load_pdfs()` by filename match. The catalog is alphabetically first in `./data/` (starts with "2") and takes 20-40 minutes on its own.

## Running Evaluation (RAGAS)

Evaluation requires the backend running on port 8002 and `.venv-eval` activated.

```bash
# Terminal 1: start backend pointing at the index under test
.venv/bin/uvicorn query:app --port 8002

# Terminal 2: run evaluation
source .venv-eval/bin/activate
python eval/run_eval.py --output baseline   # or hires, agentic
python eval/run_eval.py --output hires --skip-ragas   # collect responses only, no scoring

# Compare runs
python eval/compare_runs.py --auto   # auto-discovers latest of each type
python eval/compare_runs.py baseline_2026-04-20.json hires_2026-04-21.json
```

Results are written to `eval/results/{prefix}_{date}.json`. Never run eval against the production Railway backend — always use localhost.

## Installing Dependencies

```bash
# Backend (macOS)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Ingestion (macOS — requires Python 3.11 via conda)
conda create -p .venv-ingest-macos python=3.11 -y
.venv-ingest-macos/bin/pip install "unstructured[local-inference,pdf]"
.venv-ingest-macos/bin/pip install -r requirements_ingestion.txt
.venv-ingest-macos/bin/pip uninstall -y pinecone-client   # remove conflicting old package
.venv-ingest-macos/bin/pip install --force-reinstall pinecone==7.3.0

# System dependencies for OCR (install once via Homebrew)
brew install tesseract poppler

# Evaluation
python3 -m venv .venv-eval
.venv-eval/bin/pip install -r eval/requirements_eval.txt

# Frontend
cd frontend && npm install
```

## Required Environment Variables

**Root `.env`** (backend + ingestion):
```
COHERE_API_KEY=...
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=...        # see Pinecone Indexes section below
XAI_API_KEY=...
PYTHONUTF8=1
ANTHROPIC_API_KEY=...          # required for RAGAS eval (Claude Haiku judge)
```

**`frontend/.env.local`** (frontend):
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Each key must be on its own line. Appending to `.env` with `echo >>` is dangerous if the file lacks a trailing newline — it will corrupt the last key.

## Pinecone Indexes

There are two indexes — **do not mix them up**:

| Index name | Purpose | Status |
|---|---|---|
| `ask-testudo` | Production index (fast strategy, old corpus) | Live on Railway, do not delete |
| `ask-testudo-high-res` | hi_res evaluation index (current branch) | Local dev + eval only |

`PINECONE_INDEX_NAME` in `.env` currently points to `ask-testudo-high-res` for Phase 2 evaluation. Before deploying to production, switch it back to `ask-testudo` (or promote the hi_res index).

Both indexes: metric=`dotproduct`, dimension=`1024`, AWS us-east-1.

## Deployment

The backend is deployed on Railway via `Procfile`:
```
web: uvicorn query:app --host 0.0.0.0 --port $PORT
```

CORS in `query.py` allows `localhost:3000` and `*.vercel.app` origins. The frontend calls `/ping` on load to warm Railway cold starts.

**Production uses `ask-testudo` index.** Railway reads `PINECONE_INDEX_NAME` from its environment variables, which are set separately from the local `.env` file.

## Architecture

### Parent-Child Chunk Design

The core architectural pattern: Pinecone stores **small child chunks** (~600 chars) for precise retrieval signal, but the LLM receives **large parent chunks** (~3000 chars) for sufficient context.

- **Child chunks** live in Pinecone as dense+sparse vectors. Their metadata includes `parent_id`, `chunk_index`, `source`, `page`, `doc_type`, `file_hash`, and `text` (500-char truncation for console debugging). There is **no `child_id` field in Pinecone metadata** — the vector's Pinecone ID is the child ID.
- **Parent chunks** live on disk at `./store/parent_chunks/{parent_id}.json`. Each file contains `page_content` and `metadata`. These are what gets reranked and sent to the LLM.
- `parent_id` is a deterministic UUID5 derived from `source + page_content[:64]`. Re-ingesting unchanged files produces identical IDs. **Known limitation:** if multiple chunks from the same file share the same first 64 characters (e.g. repeated page headers), they collide and the later one overwrites the earlier on disk. The ingestion log records actual disk count (post-dedup), not raw count.

### Backend API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ask` | Main query endpoint (production) |
| `POST` | `/ask_with_contexts` | Eval-only endpoint — same as `/ask` but includes `retrieved_contexts` in response |
| `GET` | `/health` | Returns index vector count, parent chunks on disk, BM25 vocab size |
| `GET` | `/ping` | Returns `{"status": "warm"}` — used to wake Railway cold starts |

**`POST /ask` request body:**
```json
{
  "question": "string (1–500 chars)",
  "stream": false,
  "history": [{"role": "user|assistant", "content": "..."}]
}
```

**`POST /ask` response:**
```json
{
  "answer": "...",
  "sources": [...],
  "confidence": "high|medium|low",
  "rerank_score": 0.0,
  "fallback": false
}
```

**`POST /ask_with_contexts` response** adds:
```json
{
  "retrieved_contexts": ["full text of parent chunk 1", "..."]
}
```

When `stream: true`, returns SSE events with `type: "chunk"`, `"done"`, or `"error"`.

### Query Pipeline Steps (in `query.py`)

1. **Decompose** — Grok generates `sub_queries` (2–3 focused retrieval strings) + `hyde_document` (a hypothetical policy excerpt for HyDE embedding). Falls back to raw question if Grok fails.
2. **Retrieve** — `PineconeHybridSearchRetriever` is called once per query string (sub_queries + hyde). Uses `alpha=0.5` (50% dense Cohere, 50% sparse BM25), `top_k=15`. Deduplication key is `f"{parent_id}_{chunk_index}"` (synthetic — derived from Pinecone metadata fields that do exist).
3. **Parent swap** — Loads parent JSON files from disk using `parent_id` from each child's metadata. Up to 10 unique parents.
4. **Rerank** — Cohere `rerank-v3.5` cross-encoder rescores parents against the original question. Returns top 8.
5. **CRAG filter** — If top rerank score < `CRAG_THRESHOLD` (0.30), returns a fallback answer with UMD resource links instead of generating.
6. **Generate** — Grok produces an answer grounded in the top-ranked parent chunks. Inline citations required by system prompt. Up to 6 history messages are passed for conversational context.
7. **Format** — Returns `answer`, `sources`, `confidence` (high/medium/low), `rerank_score`, `fallback`.

**Confidence thresholds:** ≥0.50 = "high", ≥0.30 = "medium", <0.30 = "low"

### Key Configuration Constants (in `query.py`)

- `CRAG_THRESHOLD = 0.30` — minimum rerank score to proceed to generation
- `alpha = 0.5` — hybrid search weight (50% dense, 50% sparse)
- `top_k = 15` — child chunks retrieved per query
- `top_n = 8` — parent chunks passed to reranker
- LLM: `grok-4-1-fast-non-reasoning`, `max_tokens=1500`, `temperature=0.1`

### Shared Resources (loaded once at startup via `lifespan`)

All clients are module-level globals initialised in `lifespan()`: `pinecone_index`, `bm25_encoder`, `cohere_embeddings`, `retriever`, `cohere_client`, `xai_client`, `bm25_vocab_size`. The `PineconeHybridSearchRetriever` must be initialised with `text_key="text"` — Pinecone stores the chunk text under the key `"text"`, not the default `"context"`.

### Prompts (`query_prompts.py`)

- `DECOMPOSE_PROMPT` — instructs Grok to return strict JSON with `sub_queries` and `hyde_document`. Uses UMD-specific terminology in the HyDE prompt.
- `SYSTEM_PROMPT` — instructs the answer LLM to cite every claim, never invent policy details, and note conflicting sources.
- `build_context_prompt()` — formats parent chunks into numbered `[Document N]` blocks with source/page/section headers.

### Frontend Architecture (`frontend/`)

Built with Next.js 16.2.1 (App Router), React 19, TypeScript, and Tailwind CSS 4.

**UI design:** Perplexity-style dark layout. Default mode is dark (charcoal `#1a1a1a` background, UMD red `#D53E0F` accent). Two-state layout — centered empty state that animates into an active chat view when the first message is sent. No persistent top bar.

**Key files:**
- `app/layout.tsx` — Root layout; `class="dark"` on `<html>` sets dark mode as the default
- `app/chat/page.tsx` — Two-state chat page: empty state (title + input centered) and active state (title animates top-left via Framer Motion `layoutId`, messages fill middle, input pinned bottom). Calls `pingBackend()` on mount. "New chat" + `ThemeToggle` buttons appear top-right once a conversation starts.
- `components/ChatThread.tsx` — Message list using `StickToBottom` from `use-stick-to-bottom`; auto-scrolls during updates but respects manual scroll-up
- `components/MessageBubble.tsx` — User messages: right-aligned dark bubble. Assistant messages: `✦ Answer` header in UMD red, then markdown body, then sources/confidence badge below (no bubble wrapper)
- `components/ExampleQuestions.tsx` — Suggestion chips shown in the empty state below the input
- `components/SourceCard.tsx` — Expandable citation card (document, page, section)
- `components/ConfidenceBadge.tsx` — Confidence pill (high/medium/low)
- `components/ThemeToggle.tsx` — Defaults to dark; only switches to light if user explicitly set `"light"` in localStorage
- `components/ui/ai-prompt-box.tsx` — Custom prompt input; send button is UMD red when there is input
- `hooks/useChat.ts` — State management; calls `askQuestion()`, maintains history
- `lib/api.ts` — `askQuestion()` (POST /ask) and `pingBackend()` (GET /ping)
- `lib/types.ts` — TypeScript interfaces: `ChatMessage`, `AskResponse`, `Source`, `HistoryMessage`

**Color palette (dark mode):**
All components use `var(--umd-*)` CSS variables defined in `app/globals.css` so both dark and light modes work. Key dark-mode values: `--umd-bg: #1a1a1a`, `--umd-surface: #242424`, `--umd-border: #3a3a3a`, `--umd-text: #f5f5f5`, `--umd-muted: #808080`, `--umd-dark: #D53E0F` (accent/red).

**Deleted:** `components/Navbar.tsx` — replaced by inline controls in `chat/page.tsx`.

### Ingestion Flow (`ingest.py`)

PDF → `unstructured.partition_pdf` (`hi_res` strategy, or `ocr_only` for Academic Catalog) → `chunk_by_title` (parent chunks, max 3000 chars) → `RecursiveCharacterTextSplitter` (child chunks, ~600 chars, 60-char overlap) → Cohere embed (batch 96) + BM25 encode → Pinecone upsert (batch 100). Parents written to `./store/parent_chunks/`. BM25 fitted on child corpus, saved to `./store/bm25_encoder.json`.

Markdown support is implemented in `load_markdowns()` but intentionally disabled in `main()` (see comment in `ingest.py:151`).

**Chunk parameters (current hi_res config):**
- Parent: `max_characters=3000`, `new_after_n_chars=2500`, `combine_text_under_n_chars=300`
- Child: `chunk_size=600`, `chunk_overlap=60`

### Pinecone Index Requirements

- Metric: **dotproduct** (required for hybrid sparse-dense search — cosine will break it)
- Dimension: **1024** (Cohere `embed-english-v3.0`)

### Store Directory

```
store/
├── bm25_encoder.json     # Serialised BM25 (fitted on child corpus)
├── ingestion_log.json    # Ingestion metadata (total counts, file hashes, pipeline_version)
└── parent_chunks/        # ~10,100 JSON files, one per parent chunk (hi_res corpus)
```

`store/` is gitignored. The store must be present for the query server to start.

**hi_res corpus stats (as of 2026-04-21):**
- 311 PDFs in `./data/`
- 10,098 unique parent chunks on disk
- 17,557 child vectors in `ask-testudo-high-res`
- 31,110 BM25 vocabulary terms

### Evaluation Infrastructure (`eval/`)

```
eval/
├── golden_dataset.json        # 60 QA pairs (fixed — do not modify between runs)
├── run_eval.py                # RAGAS runner — calls /ask_with_contexts on localhost:8002
├── compare_runs.py            # Side-by-side comparison + bar chart
├── requirements_eval.txt      # Eval-only deps (ragas, anthropic, etc.)
└── results/
    ├── baseline_YYYY-MM-DD.json
    ├── hires_YYYY-MM-DD.json
    ├── comparison.png
    └── phase2_analysis.md
```

**RAGAS judge:** Claude Haiku (`claude-haiku-4-5-20251001`) via `ANTHROPIC_API_KEY`. Never use Grok as the judge — an LLM evaluating its own output inflates scores.

**Phase 2 RAGAS results (baseline → hi_res):**

| Metric | Baseline | hi_res | Delta |
|---|---|---|---|
| context_precision | 0.2027 | 0.1684 | -0.034 |
| context_recall | 0.2370 | 0.2919 | +0.055 |
| faithfulness | 0.4411 | 0.5300 | +0.089 |
| answer_relevancy | 0.5671 | 0.6216 | +0.055 |

Phase 3 (agentic web search) is the next step per `plan2.md`.
