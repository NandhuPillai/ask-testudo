# ask-testudo Query Pipeline — Catchup Document

## What This Is

**ask-testudo** is a FastAPI-based question-answering service for University of Maryland students. You ask it a natural-language question about academic policy (graduation requirements, GPA thresholds, registration rules, degree requirements, etc.) and it returns a grounded answer with citations pulled directly from official UMD documents.

The pipeline is a **RAG (Retrieval-Augmented Generation)** system with several layers on top of basic RAG: query decomposition, hybrid search, parent-document retrieval, cross-encoder reranking, and a CRAG (Corrective RAG) confidence filter. These layers exist to make answers more accurate and less prone to hallucination than a plain LLM call.

---

## Repository Layout

```
C:\ask-testudo\
├── query.py                  # FastAPI app — the entire query pipeline lives here
├── query_prompts.py          # LLM prompt templates (decompose + answer generation)
├── requirements.txt          # Runtime dependencies for the query server
├── requirements_ingestion.txt# Dependencies used only during ingestion (separate)
├── .env                      # API keys (not committed)
├── .venv/                    # Isolated Python virtual environment
├── store/
│   ├── bm25_encoder.json     # Serialised BM25 sparse encoder (fitted during ingestion)
│   └── parent_chunks/        # ~8,700 JSON files, one per parent document chunk
├── data/                     # Source PDFs (academic catalog, major requirements, etc.)
├── ingest.py                 # Ingestion pipeline (run once, not part of the query server)
├── verify_ingestion.py       # Verification script for ingestion output
├── download_pdfs.py          # PDF downloader used to populate data/
├── collect_priority_1.py     # Helper for collecting priority PDFs
└── output.log                # Original error log from the failed base-env run
```

---

## Technologies Used

| Technology | Role |
|---|---|
| **FastAPI** | HTTP server framework. Exposes `/ask` and `/health` endpoints. |
| **uvicorn** | ASGI server that runs the FastAPI app. |
| **Pinecone** | Serverless vector database. Stores ~33,000 dense+sparse vectors (one per child chunk). |
| **Cohere `embed-english-v3.0`** | Dense embedding model. Converts text to 1024-dim vectors for semantic search. |
| **Cohere `rerank-v3.5`** | Cross-encoder reranker. Re-scores retrieved parent documents against the original question. |
| **pinecone-text `BM25Encoder`** | Sparse encoder for keyword-based (BM25) retrieval. Fitted on the corpus during ingestion. |
| **`PineconeHybridSearchRetriever`** | LangChain retriever that fuses dense + sparse scores in Pinecone (alpha-weighted). |
| **xAI Grok (`grok-4-1-fast-non-reasoning`)** | LLM used for two things: query decomposition (Step 1) and answer generation (Step 6). |
| **LangChain** | Provides the retriever abstraction and Cohere embeddings integration. |
| **python-dotenv** | Loads API keys from `.env` at startup. |
| **pydantic** | Request validation (`AskRequest` model). |

---

## The Data: What Was Ingested

Ingestion is a one-time process (run separately via `ingest.py`) that produced:

- **~33,000 child chunks** — short overlapping text segments stored as dense+sparse vectors in Pinecone. Each vector's metadata contains `parent_id`, `chunk_index`, `source`, `page`, `doc_type`, `file_hash`, and `text` (a 500-char excerpt).
- **~8,700 parent chunk JSON files** in `./store/parent_chunks/` — larger text segments (full paragraphs or sections). Each file is named `{parent_id}.json` and contains `page_content` and `metadata`. The parent chunks are what the LLM actually reads.
- **`bm25_encoder.json`** — the fitted BM25 sparse encoder, serialised so it can be loaded at query time without re-fitting.

The **parent-child relationship** is the core design choice: Pinecone is searched using small, precise child chunks (better retrieval signal), but the LLM is given the larger parent chunks (more context, better answer quality). The `parent_id` field on every Pinecone vector is the link between the two.

Source documents are official UMD PDFs: the Academic Catalog, individual major requirement sheets, grad plans, and policy documents.

---

## The 7-Step Query Pipeline

Every call to `POST /ask` runs these steps in sequence:

### Step 1 — Query Decomposition (`decompose_query`)

**File:** `query.py:167`, prompts in `query_prompts.py`

The raw student question is sent to Grok with a structured prompt. Grok returns a JSON object with two fields:

```json
{
  "sub_queries": ["GPA requirement for graduation", "minimum cumulative GPA UMD", "academic standing requirements"],
  "hyde_document": "Students must maintain a minimum cumulative GPA of 2.0 to satisfy graduation requirements..."
}
```

- `sub_queries` — 2–3 short, distinct retrieval strings targeting different aspects of the question. These prevent a single embedding from missing relevant documents.
- `hyde_document` — a **HyDE (Hypothetical Document Embedding)** snippet. Instead of embedding the question itself, this embeds a synthetic answer written in the style of the source documents. HyDE improves recall because the embedding of a policy-style answer is closer to actual policy text than the embedding of a casual question.

If Grok fails or returns malformed JSON, the step falls back to using the raw question for both fields.

### Step 2 — Hybrid Retrieval (`retrieve_chunks`)

**File:** `query.py:200`

All sub-queries plus the HyDE document are used as retrieval queries (typically 4 total). For each query, `PineconeHybridSearchRetriever.invoke()` is called, which:

1. Encodes the query text into a **dense vector** using Cohere `embed-english-v3.0`
2. Encodes the query text into a **sparse vector** using the fitted BM25 encoder
3. Sends both to Pinecone's hybrid search API, which scores candidates as: `score = alpha * dense_score + (1 - alpha) * sparse_score` with `alpha=0.6` (60% semantic, 40% keyword)
4. Returns the top 10 child chunk documents

Results across all queries are deduplicated using a synthetic `child_id = f"{parent_id}_{chunk_index}"` key (since Pinecone metadata does not include a standalone child ID field). Up to 10 unique child chunks are returned.

### Step 3 — Parent Swap (`swap_to_parents`)

**File:** `query.py:221`

Each child chunk has a `parent_id` in its Pinecone metadata. This step:

1. Collects all unique `parent_id` values from the retrieved child chunks
2. For each unique parent ID, loads `./store/parent_chunks/{parent_id}.json` from disk
3. Returns a list of parent document dicts (each with `page_content` and `metadata`)

This replaces the small child chunks with their larger parent passages. The LLM never sees the child chunks — only the parents.

### Step 4 — Reranking (`rerank_parents`)

**File:** `query.py:250`

The parent chunks are reranked using Cohere's **`rerank-v3.5`** cross-encoder model. Unlike embedding-based retrieval (which compares vectors independently), a cross-encoder reads the query and each document together and outputs a relevance score. This is slower but much more accurate.

- Input: up to ~10 parent chunks + the original question
- Output: top 4 parent chunks sorted by relevance, plus the top relevance score

The top relevance score (0.0–1.0) is used in the next step.

### Step 5 — CRAG Confidence Filter

**File:** `query.py:443`

**CRAG = Corrective RAG.** If the reranker's top score is below `CRAG_THRESHOLD = 0.30`, it means the retrieved documents are not relevant enough to answer the question reliably. Instead of hallucinating, the pipeline returns a fallback response:

```
"I don't have reliable information in my knowledge base to answer this confidently.
For accurate information I'd recommend:
- UMD Registrar: registrar.umd.edu
..."
```

The fallback response is returned with `"fallback": true` and `"confidence": "low"`. If the score is ≥ 0.30, the pipeline continues to generation.

### Step 6 — Answer Generation (`generate_answer`)

**File:** `query.py:272`

The top 4 reranked parent chunks are formatted into a context block and sent to Grok along with the original student question. The system prompt (`SYSTEM_PROMPT` in `query_prompts.py`) instructs the model to:

- Answer using only the provided context documents
- Include inline citations (`[Source: filename, Page: N]`) for every factual claim
- Never invent course numbers, credit hours, GPA thresholds, or deadlines
- Flag conflicts between sources
- Stay student-friendly

The model generates up to 800 tokens with `temperature=0.1` (nearly deterministic). Streaming is supported via Server-Sent Events.

### Step 7 — Response Formatting (`format_response`)

**File:** `query.py:328`

The final JSON response is assembled:

```json
{
  "answer": "The minimum GPA required to graduate...",
  "sources": [
    {"filename": "animal-sciences-major.pdf", "page": 3, "section": "", "doc_type": "pdf"}
  ],
  "confidence": "high",
  "rerank_score": 0.7218,
  "fallback": false
}
```

Confidence labels map from the rerank score:
- `"high"` — score ≥ 0.50
- `"medium"` — score ≥ 0.30
- `"low"` — score < 0.30 (fallback path, never reaches generation)

---

## Startup Sequence

When uvicorn starts the app, the `lifespan` function (`query.py:64`) runs once and initialises all shared resources as module-level globals:

1. Load API keys from `.env`, validate all four are present
2. Load and deserialise `BM25Encoder` from `./store/bm25_encoder.json`
3. Connect to Pinecone and verify the index is reachable
4. Count parent chunk files on disk
5. Initialise `CohereEmbeddings` (dense encoder)
6. Construct the `PineconeHybridSearchRetriever` with `text_key="text"`, `top_k=10`, `alpha=0.6`
7. Initialise Cohere rerank client
8. Initialise xAI (Grok) client via the OpenAI-compatible SDK

All resources are held in memory for the lifetime of the process. Startup failure on any step raises `RuntimeError` and prevents the server from accepting requests.

---

## Environment Variables (`.env`)

```
COHERE_API_KEY=...        # Cohere API key (embeddings + reranking)
PINECONE_API_KEY=...      # Pinecone API key
PINECONE_INDEX_NAME=...   # Pinecone index name (e.g. "ask-testudo")
XAI_API_KEY=...           # xAI API key (Grok)
PYTHONUTF8=1              # Forces UTF-8 I/O on Windows (prevents cp1252 codec errors)
```

Each key must be on its own line. The `PYTHONUTF8=1` line must not be appended to the end of the last key line — check with `tail -5 .env` if you see odd API key errors.

---

## How to Run

### Prerequisites

- Python 3.9 (the `.venv` was created with the system Python 3.9.13)
- All four API keys in `.env`
- Ingestion already completed (`./store/` populated)

### Start the server

```bash
cd C:\ask-testudo
.venv\Scripts\uvicorn query:app --host 0.0.0.0 --port 8000
```

Add `--reload` during development to auto-restart on file changes. Note: on Windows with `--reload`, uvicorn uses WatchFiles which forks a watcher process. After a reload, the new worker's stdout may not be captured in a redirected log file — use foreground mode (no `&`) for reliable log output.

### Health check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "index_vector_count": 32965,
  "parent_chunks_on_disk": 8707,
  "bm25_vocabulary_size": 2
}
```

Note: `bm25_vocabulary_size: 2` is a display artifact — the BM25 encoder's `doc_freq` field is stored in sparse format (`{"indices": [...], "values": [...]}`) so the code counts 2 top-level keys instead of actual vocabulary terms. The encoder itself works correctly.

### Ask a question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the minimum GPA required to graduate?"}'
```

### Ask with streaming (SSE)

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the requirements for the CS major?", "stream": true}'
```

Streaming returns Server-Sent Events. Each `data:` line is a JSON object:
- `{"type": "chunk", "content": "..."}` — incremental answer text
- `{"type": "done", "sources": [...], "confidence": "...", "rerank_score": 0.72}` — final metadata
- `{"type": "error", "detail": "..."}` — if generation fails mid-stream

---

## Issues Encountered and Fixes Applied

### Issue 1 — numpy/scikit-learn Binary Incompatibility

**Symptom:** The server crashed immediately at import time when run in the base Anaconda environment:

```
ValueError: numpy.dtype size changed, may indicate binary incompatibility.
Expected 96 from C header, got 88 from PyObject
```

**Import chain that triggered it:**
```
query.py
  → pinecone_text.sparse.BM25Encoder
    → pinecone_text.sparse.bm25_tokenizer
      → nltk
        → nltk.classify.scikitlearn
          → sklearn.utils.murmurhash  ← compiled against a different numpy
            → ValueError
```

The base Anaconda environment had a sklearn binary compiled against a different version of numpy than was currently installed. This is a known hazard of conda environments where packages are updated independently.

**Fix:** Created an isolated virtual environment (`.venv`) and installed all dependencies fresh:

```bash
python -m venv .venv
.venv\Scripts\pip install --prefer-binary -r requirements.txt
```

The `--prefer-binary` flag tells pip to download pre-built `.whl` wheels instead of compiling from source, which avoids the need for Microsoft C++ Build Tools (a 6 GB install). This gives numpy and scikit-learn a clean, consistent install with no version mismatch.

---

### Issue 2 — `pinecone-client` vs `pinecone` Package Name

**Symptom:** `requirements.txt` listed `pinecone-client` (the legacy package name). The code uses `from pinecone import Pinecone` which requires the modern `pinecone` SDK (v3+).

**Fix:** Changed line 7 of `requirements.txt`:
```
# Before
pinecone-client

# After
pinecone
```

---

### Issue 3 — `greenlet` Required C++ Compiler

**Symptom:** During `pip install`, `greenlet` (a transitive dependency pulled in by `langchain-community → SQLAlchemy → greenlet`) tried to compile from source and failed:

```
error: Microsoft Visual C++ 14.0 or greater is required.
```

**Fix:** The `--prefer-binary` flag resolved this — pip downloaded the pre-built `greenlet-3.2.4` wheel for `cp39-win_amd64`. To make this reproducible and explicit, `requirements.txt` was also updated to pin:

```
greenlet==3.1.1
SQLAlchemy==2.0.36
numpy>=1.26,<2.0
```

Pinning `greenlet==3.1.1` ensures a version with a known Windows binary wheel. Pinning `SQLAlchemy` alongside it ensures a compatible pair.

---

### Issue 4 — `retrieve_chunks` Used Non-Existent `child_id` Metadata Field

**Symptom:** Every call to `/ask` returned:
```json
{"error": "parent swap failed", "detail": "no parent documents found after swap"}
```

The retriever was being called (4 Cohere embed API calls appeared in the logs) but `swap_to_parents` received an empty list.

**Root cause:** `retrieve_chunks` deduplicated results using:
```python
child_id = doc.metadata.get("child_id")
if child_id and child_id not in seen:
    seen[child_id] = doc
```

But Pinecone vector metadata does not contain a `child_id` field. The actual fields stored during ingestion are: `parent_id`, `chunk_index`, `source`, `page`, `doc_type`, `file_hash`, `text`. Because `child_id` was always `None`, the `if child_id` check always failed, `seen` was never populated, and `retrieve_chunks` always returned `[]`.

**Fix:** Construct a synthetic child ID from the fields that do exist:
```python
parent_id = doc.metadata.get("parent_id")
chunk_index = int(doc.metadata.get("chunk_index", 0))
child_id = f"{parent_id}_{chunk_index}" if parent_id else None
if child_id and child_id not in seen:
    seen[child_id] = doc
```

This creates a unique key per child chunk. The `int()` cast handles the fact that Pinecone returns numeric metadata as floats (`chunk_index: 2.0`).

---

### Issue 5 — `PYTHONUTF8=1` Corrupted the XAI API Key

**Symptom:** After adding `PYTHONUTF8=1` to `.env` using `echo "PYTHONUTF8=1" >> .env`, the xAI generation step failed with:

```
Error code: 400 - Incorrect API key provided: xa***=1
```

**Root cause:** The `.env` file did not have a trailing newline after `XAI_API_KEY`. The `echo >>` command appended directly to the last line, producing:

```
XAI_API_KEY=xai-...Vjq4RPYTHONUTF8=1
```

`python-dotenv` parsed the entire thing as the value of `XAI_API_KEY`.

**Fix:** Edited `.env` directly to restore the correct API key on its own line and put `PYTHONUTF8=1` on a separate line beneath it. Always use an editor (not shell append) when modifying `.env`.

---

### Issue 6 — uvicorn `--reload` on Windows Breaks Log Capture

**Symptom (operational, not a code bug):** When uvicorn is started with `--reload` and stdout is redirected (e.g. to a log file or background task), after the first reload event the new worker process's stdout is no longer captured. The output file freezes, making it impossible to see whether subsequent code changes took effect.

**What happens:** `--reload` spawns a WatchFiles watcher process (the main process) and a separate server worker subprocess. When a file change is detected, the watcher kills the worker and starts a new one. The new worker's stdout is not inherited by the redirected stream.

**Workaround:** Run uvicorn in the foreground without output redirection during development:
```bash
.venv\Scripts\uvicorn query:app --host 0.0.0.0 --port 8000 --reload
```
Or omit `--reload` in production and restart manually.

---

## Confirmed Working Output

After all fixes, a test query returned:

```json
{
  "answer": "The minimum GPA required to graduate varies by major but is consistently a cumulative 2.0 GPA and a 2.0 GPA in major requirements across the provided documents:\n\n- Animal Sciences (ANSC): Cumulative GPA of at least 2.0 [Source: animal-sciences-major.pdf, Page: 3]\n- Landscape Architecture (LARC): Cumulative GPA of at least 2.0 [Source: landscape-architecture-major.pdf, Page: 2]\n- Electrical Engineering (ENEE): Minimum 2.00 cumulative UM GPA [Source: electrical-fall-2025-gradplan-ADA.pdf, Page: 1]",
  "sources": [
    {"filename": "animal-sciences-major.pdf", "page": 3, "section": "", "doc_type": "pdf"},
    {"filename": "landscape-architecture-major.pdf", "page": 2, "section": "", "doc_type": "pdf"},
    {"filename": "electrical-fall-2025-gradplan-ADA.pdf", "page": 1, "section": "", "doc_type": "pdf"},
    {"filename": "fire-protection-fall-2025-gradplan-ADA.pdf", "page": 1, "section": "", "doc_type": "pdf"}
  ],
  "confidence": "high",
  "rerank_score": 0.7218,
  "fallback": false
}
```

`rerank_score: 0.7218` is well above the `CRAG_THRESHOLD` of 0.30. `fallback: false` confirms the pipeline found genuinely relevant documents and generated a grounded answer.

---

## Quick Reference

| What | Command |
|---|---|
| Start server | `.venv\Scripts\uvicorn query:app --host 0.0.0.0 --port 8000` |
| Health check | `curl http://localhost:8000/health` |
| Ask a question | `curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d "{\"question\": \"...\"}"` |
| Install deps | `.venv\Scripts\pip install --prefer-binary -r requirements.txt` |
| Activate venv | `.venv\Scripts\activate` |
