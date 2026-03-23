# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**ask-testudo** is a RAG-based question-answering API for University of Maryland academic policy. Students ask natural-language questions; the system retrieves relevant passages from official UMD PDFs and generates grounded answers with citations.

There are two completely separate pipelines with separate dependency sets:
- **Ingestion** (`ingest.py`) — one-time process that parses PDFs, creates parent/child chunks, fits BM25, embeds with Cohere, and upserts to Pinecone.
- **Query** (`query.py`) — FastAPI server that handles live question answering. This is what runs in production.

## Running the Query Server

All commands use the `.venv` virtual environment, not the system/Anaconda Python.

```bash
# Start the server
.venv\Scripts\uvicorn query:app --host 0.0.0.0 --port 8000

# With auto-reload during development (note: on Windows, stdout capture breaks after first reload)
.venv\Scripts\uvicorn query:app --host 0.0.0.0 --port 8000 --reload

# Health check
curl http://localhost:8000/health

# Ask a question
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the minimum GPA to graduate?"}'

# Streaming response (SSE)
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the CS major requirements?", "stream": true}'
```

## Running Ingestion

Ingestion has a separate requirements file (`requirements_ingestion.txt`) because it needs `unstructured` (for PDF parsing), which is not needed at query time.

```bash
# Verify ingestion output is healthy (run from repo root)
.venv\Scripts\python verify_ingestion.py

# Re-run ingestion (only if source PDFs changed — very slow, makes API calls)
.venv\Scripts\python ingest.py
```

## Installing Dependencies

```bash
python -m venv .venv
.venv\Scripts\pip install --prefer-binary -r requirements.txt
```

The `--prefer-binary` flag is required on Windows to avoid compiling `greenlet` from source (which requires MSVC). `greenlet` and `SQLAlchemy` are pinned at the top of `requirements.txt` for this reason.

## Required Environment Variables (`.env`)

```
COHERE_API_KEY=...
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=...
XAI_API_KEY=...
PYTHONUTF8=1
```

Each key must be on its own line. Appending to `.env` with `echo >>` is dangerous if the file lacks a trailing newline — it will corrupt the last key.

## Architecture

### Parent-Child Chunk Design

The core architectural pattern: Pinecone stores **small child chunks** (~300 chars) for precise retrieval signal, but the LLM receives **large parent chunks** (~1500 chars) for sufficient context.

- **Child chunks** live in Pinecone as dense+sparse vectors. Their metadata includes `parent_id`, `chunk_index`, `source`, `page`, `doc_type`, `file_hash`, and `text` (500-char truncation for console debugging). There is **no `child_id` field in Pinecone metadata** — the vector's Pinecone ID is the child ID.
- **Parent chunks** live on disk at `./store/parent_chunks/{parent_id}.json`. Each file contains `page_content` and `metadata`. These are what gets reranked and sent to the LLM.
- `parent_id` is a deterministic UUID5 derived from `source + page_content[:64]`, so re-ingesting unchanged files produces identical IDs (no duplicates).

### Query Pipeline Steps (in `query.py`)

1. **Decompose** — Grok generates `sub_queries` (2–3 focused retrieval strings) + `hyde_document` (a hypothetical policy excerpt for HyDE embedding). Falls back to raw question if Grok fails.
2. **Retrieve** — `PineconeHybridSearchRetriever` is called once per query string (sub_queries + hyde). Uses `alpha=0.6` (60% dense Cohere, 40% sparse BM25), `top_k=10`. Deduplication key is `f"{parent_id}_{chunk_index}"` (synthetic — derived from Pinecone metadata fields that do exist).
3. **Parent swap** — Loads parent JSON files from disk using `parent_id` from each child's metadata. Up to 10 unique parents.
4. **Rerank** — Cohere `rerank-v3.5` cross-encoder rescores parents against the original question. Returns top 4.
5. **CRAG filter** — If top rerank score < `CRAG_THRESHOLD` (0.30), returns a fallback answer with UMD resource links instead of generating.
6. **Generate** — Grok produces an answer grounded in the top 4 parent chunks. Inline citations required by system prompt.
7. **Format** — Returns `answer`, `sources`, `confidence` (high/medium/low), `rerank_score`, `fallback`.

### Key Configuration Constants (in `query.py`)

- `CRAG_THRESHOLD = 0.30` — minimum rerank score to proceed to generation
- `alpha = 0.6` — hybrid search weight (dense vs sparse)
- `top_k = 10` — child chunks retrieved per query
- `top_n = 4` — parent chunks passed to rerank and then to LLM
- LLM: `grok-4-1-fast-non-reasoning`, `max_tokens=800`, `temperature=0.1`

### Shared Resources (loaded once at startup via `lifespan`)

All clients are module-level globals initialised in `lifespan()`: `pinecone_index`, `bm25_encoder`, `cohere_embeddings`, `retriever`, `cohere_client`, `xai_client`. The `PineconeHybridSearchRetriever` must be initialised with `text_key="text"` — Pinecone stores the chunk text under the key `"text"`, not the default `"context"`.

### Prompts (`query_prompts.py`)

- `DECOMPOSE_PROMPT` — instructs Grok to return strict JSON with `sub_queries` and `hyde_document`. Uses UMD-specific terminology in the HyDE prompt.
- `SYSTEM_PROMPT` — instructs the answer LLM to cite every claim, never invent policy details, and note conflicting sources.
- `build_context_prompt()` — formats parent chunks into numbered `[Document N]` blocks with source/page/section headers.

### Ingestion Flow (`ingest.py`)

PDF → `unstructured.partition_pdf` (fast strategy) → `chunk_by_title` (parent chunks, ~1500 chars) → `RecursiveCharacterTextSplitter` (child chunks, ~300 chars, 30-char overlap) → Cohere embed (batch 96) + BM25 encode → Pinecone upsert (batch 100). Parents written to `./store/parent_chunks/`. BM25 fitted on child corpus, saved to `./store/bm25_encoder.json`.

Markdown support is implemented in `load_markdowns()` but intentionally disabled in `main()` (see comment in `ingest.py:151`).

### Pinecone Index Requirements

- Metric: **dotproduct** (required for hybrid sparse-dense search — cosine will break it)
- Dimension: **1024** (Cohere `embed-english-v3.0`)

### Store Directory

```
store/
├── bm25_encoder.json     # Serialised BM25 (fitted on child corpus)
├── ingestion_log.json    # Ingestion metadata (total counts, file hashes)
└── parent_chunks/        # ~8,700 JSON files, one per parent chunk
```

`store/` is gitignored (as `.store/` — note the dot in `.gitignore` is a typo, the actual directory is `store/`). The store must be present for the query server to start.
