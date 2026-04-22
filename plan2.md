# ask-testudo — RAGAS Evaluation & hi_res Re-ingestion Plan

## Project context (must read before any task)

ask-testudo is a production RAG system for UMD students to query academic
policies, course requirements, and registration procedures. The system is
deployed with a FastAPI backend on Railway and a Next.js frontend on Vercel.

### Current pipeline architecture

```
Student question
    ↓
1. Query decomposer (Grok-4-1-fast-non-reasoning → 2-3 sub-queries + HyDE doc)
    ↓
2. Hybrid retrieval (PineconeHybridSearchRetriever, alpha=0.6, top_k=10)
    ↓
3. Parent chunk swap (child parent_id → full parent from ./store/parent_chunks/)
    ↓
4. Reranking (Cohere rerank-v3.5, top_n=4, threshold 0.30)
    ↓
5. CRAG check (if top score < 0.30, return fallback response)
    ↓
6. Answer generation (Grok-4-1-fast-non-reasoning, grounded prompt)
    ↓
Response with citations + confidence badge
```

### Known problems the current system has

1. **Chunking boundary failures.** `chunk_by_title(max_characters=1500)` in
   `ingest.py` splits requirements tables mid-list. Observed case: CS major
   lower-level requirements table gets cut after CMSC132, losing CMSC216 and
   CMSC250 from retrieval despite being in the corpus.

2. **`strategy="fast"` limits.** Current PDF parsing uses pdfminer which
   reads linearly by coordinate. For multi-column layouts (academic catalog,
   policy handbooks) columns get interleaved and tables lose structure.

3. **No evaluation baseline.** Quality improvements have been subjective
   ("feels better") rather than measured. No way to know which change
   actually helped.

### Corpus state

- 261 PDFs in `./data/` (major/minor requirement sheets, registration guide,
  2025-2026 Academic Catalog, other policy documents)
- 9,095 parent chunks in `./store/parent_chunks/`
- 34,870 children indexed in Pinecone (metric=dotproduct, dim=1024)
- BM25 encoder at `./store/bm25_encoder.json` with 8,792 terms

### Hardware change

This work is being done on an M5 Pro MacBook Pro, not the previous Windows
machine. This enables:
- Native Apple Silicon PyTorch via MPS (Metal Performance Shaders)
- `strategy="hi_res"` with detectron2 in ~2-3 hours for full corpus
  (vs 30+ hours on Windows CPU)
- No more Visual C++ Build Tools / WSL requirements

### Stack reference

- Python 3.11+
- `unstructured[pdf]`, `pdfminer.six`, `pytesseract`, `pdf2image`
- `langchain`, `langchain-cohere`, `langchain-community`, `langchain-pinecone`
- `pinecone-text`, `pinecone` (v3 SDK)
- `cohere` (for reranking)
- `openai` SDK pointed at xAI (`base_url="https://api.x.ai/v1"`)
- Environment variables in `.env`: `COHERE_API_KEY`, `PINECONE_API_KEY`,
  `PINECONE_INDEX_NAME`, `XAI_API_KEY`

---

## Goal of this plan

Improve the RAG pipeline with measurable evidence. Three phases, strict
ordering — do not skip ahead:

```
Phase 1: Build golden dataset + RAGAS baseline on current system
Phase 2: hi_res re-ingestion on M5 Pro, RAGAS re-evaluation, compare
Phase 3: (conditional) Agentic web search if Phase 2 is insufficient
```

Each phase must produce quantitative metrics before moving to the next.

---

## PHASE 1 — Baseline Evaluation

### Phase 1 goal

Establish numeric baseline scores for the current pipeline on 4 RAGAS
metrics. These numbers are the reference point for every subsequent change.

### Step 1.1 — Build golden dataset

Create `./eval/golden_dataset.json` with 60 question/answer/ground-truth
triples drawn from actual ingested documents. Do NOT use LLM-generated
answers — ground truth must come from manual reading of source PDFs.

Distribution (match these counts exactly):

| Category | Count | Example |
|---|---|---|
| Factual lookup | 15 | "What GPA is required for Latin honors at UMD?" |
| Requirement list | 15 | "What are all lower-level requirements for the CS major?" |
| Policy question | 10 | "What is the deadline to drop a class in Fall 2025?" |
| Cross-document | 10 | "Does the CS major prerequisite policy apply to transfer students?" |
| Out-of-corpus | 10 | "What time does McKeldin library close on Sundays?" |

JSON schema for each entry:

```json
{
  "id": "q001",
  "category": "factual_lookup",
  "question": "What GPA is required for Latin honors at UMD?",
  "ground_truth_answer": "A cumulative GPA of 3.200 or higher is required...",
  "ground_truth_sources": [
    {"filename": "2025-2026 Academic Catalog.pdf", "page": 142}
  ],
  "expected_confidence": "high",
  "expected_fallback": false
}
```

For out-of-corpus questions, set `expected_fallback: true` and leave
`ground_truth_sources` as an empty array. These test whether the CRAG
threshold correctly rejects queries the system shouldn't answer.

Use realistic student phrasing — not formal policy language. Questions
should sound like something a student would actually ask a Reddit thread
or an advisor. Include typos, colloquialisms, and ambiguity in 10-15% of
questions to stress-test the system.

### Step 1.2 — Install RAGAS dependencies

Create `./eval/requirements_eval.txt`:

```
ragas>=0.2.0
datasets
pandas
matplotlib
seaborn
langchain-anthropic
anthropic
```

Install into a separate eval venv (keep isolated from query.py deps):

```bash
python3 -m venv .venv-eval
source .venv-eval/bin/activate
pip install -r eval/requirements_eval.txt
```

### Step 1.3 — Build run_eval.py

Create `./eval/run_eval.py` that:

1. Loads `golden_dataset.json`
2. For each question, calls the running `ask-testudo` backend at
   `http://localhost:8002/ask` (must be running in another terminal)
3. Captures: answer, retrieved_contexts (source filenames + page_content),
   rerank_score, confidence, fallback
4. Builds a RAGAS-compatible Dataset with fields:
   - `question`: str
   - `answer`: str (generated by ask-testudo)
   - `contexts`: list[str] (the retrieved parent chunk contents)
   - `ground_truth`: str (from golden dataset)
5. Runs RAGAS metrics:
   - `context_precision`
   - `context_recall`
   - `faithfulness`
   - `answer_relevancy`
6. Writes results to `./eval/results/baseline_YYYY-MM-DD.json` with
   per-question scores and aggregate means
7. Prints a summary table to stdout

**Critical implementation detail — RAGAS needs access to contexts.**
The running backend does not currently return retrieved contexts in the
`/ask` response. Add a new endpoint `/ask_with_contexts` that returns
everything `/ask` returns plus a `retrieved_contexts: list[str]` field
containing the page_content of each reranked parent chunk sent to the LLM.
This endpoint is for evaluation only — not exposed to the frontend.

Add to `query.py`:

```python
@app.post("/ask_with_contexts")
def ask_with_contexts(request: AskRequest):
    # Run full pipeline but return contexts too
    # Used by eval/run_eval.py only
    sub_queries_data = decompose_query(request.question)
    child_docs = retrieve_chunks(
        sub_queries_data["sub_queries"],
        sub_queries_data["hyde_document"]
    )
    parents = swap_to_parents(child_docs)
    reranked_parents, top_score = rerank_parents(parents, request.question)

    if top_score < CRAG_THRESHOLD:
        return fallback_response(top_score)

    answer = generate_answer(reranked_parents, request.question, request.history)
    response = format_response(answer, reranked_parents, top_score)
    response["retrieved_contexts"] = [
        p["page_content"] for p in reranked_parents
    ]
    return response
```

### Step 1.4 — RAGAS LLM configuration

RAGAS uses an LLM to compute some metrics (faithfulness, answer_relevancy).
Do NOT use Grok for eval — the LLM being evaluated should not evaluate
itself, as it systematically inflates scores by favoring its own output
style. Use a neutral judge from a different provider:

```python
from ragas.llms import LangchainLLMWrapper
from langchain_anthropic import ChatAnthropic

judge_llm = LangchainLLMWrapper(
    ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        temperature=0.0,
        max_tokens=1024,
    )
)
```

Also configure the embeddings model RAGAS uses for `answer_relevancy`
(it compares the semantic similarity of generated answers to questions).
Use Cohere here since you already have the key:

```python
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_cohere import CohereEmbeddings

judge_embeddings = LangchainEmbeddingsWrapper(
    CohereEmbeddings(model="embed-english-v3.0")
)
```

Requires `ANTHROPIC_API_KEY` in `.env` for eval purposes only. Cost per
baseline run with Claude Haiku 4.5: approximately $0.30-0.60 for 60
questions. Haiku is chosen over Sonnet here because RAGAS makes many
small judgment calls (yes/no faithfulness checks per claim) where
Haiku's speed and cost per call matter more than Sonnet's extra depth.

Why Claude over GPT as judge:
- Claude is a different model family than Grok (no cross-family bias)
- Claude Haiku's instruction-following for structured judgment tasks
  is excellent
- Evaluation results are more stable across runs (lower variance)

### Step 1.5 — Run baseline

Before running:
1. Start the FastAPI backend: `uvicorn query:app --port 8002`
2. Verify `/health` returns current state
3. Activate eval venv
4. Run: `python eval/run_eval.py --output baseline`

Expected output file: `./eval/results/baseline_YYYY-MM-DD.json` containing:

```json
{
  "run_id": "baseline_2026-04-17",
  "pipeline_version": "current (strategy=fast, chunk=1500)",
  "total_questions": 60,
  "metrics": {
    "context_precision": 0.XX,
    "context_recall": 0.XX,
    "faithfulness": 0.XX,
    "answer_relevancy": 0.XX
  },
  "per_category": {
    "factual_lookup":    { "context_precision": 0.XX, ... },
    "requirement_list":  { "context_precision": 0.XX, ... },
    ...
  },
  "per_question": [ ... ]
}
```

### Step 1.6 — Baseline analysis

Write a short `./eval/results/baseline_analysis.md` covering:

1. Overall scores across 4 metrics
2. Weakest metric (expected: `context_recall` due to chunking boundary bug)
3. Worst category (expected: `requirement_list`)
4. Specific failing questions to revisit after Phase 2
5. Screenshot or table comparison to the eventual Phase 2 results

This is the benchmark against which all future changes are measured.

### Phase 1 success criteria

- 60 golden dataset questions written and stored in JSON
- `/ask_with_contexts` endpoint live and tested
- RAGAS runs end-to-end without errors
- Baseline metrics file exists in `./eval/results/`
- Baseline analysis markdown written

Do NOT proceed to Phase 2 until all five criteria are met.

---

## PHASE 2 — hi_res Re-ingestion on M5 Pro
 
### Phase 2 goal
 
Replace `strategy="fast"` with `strategy="hi_res"` for PDF parsing,
increase parent chunk size to avoid boundary cutoffs, re-run full
ingestion, then re-evaluate with the same golden dataset to measure
improvement.
 
### Step 2.1 — macOS environment setup
 
Run on the M5 Pro MacBook Pro natively (not WSL, not Docker). The setup
is simpler than it was for Windows — `unstructured` ships ONNX-based
inference models that have pre-built wheels for Apple Silicon.
 
```bash
# System dependencies for PDF/OCR processing
brew install tesseract poppler
 
# Create ingestion venv (separate from query venv)
cd ~/ask-testudo
python3 -m venv .venv-ingest-macos
source .venv-ingest-macos/bin/activate
 
# Install unstructured with the local-inference extra
# This pulls in onnxruntime and detectron2_onnx automatically
pip install "unstructured[local-inference,pdf]"
 
# Install remaining ingestion deps from existing requirements file
pip install -r requirements_ingestion.txt
```
 
**Understanding the `hi_res` dependency stack:**
 
The `hi_res` strategy identifies document layout using `detectron2_onnx` —
an ONNX-exported layout detection model that runs via `onnxruntime`. This
is NOT the full Facebook detectron2 framework (which would require building
from source on Apple Silicon). It's a pre-compiled ONNX model file with
standard runtime dependencies that install cleanly from PyPI.
 
The `unstructured[local-inference]` extra is the canonical install path
documented in the unstructured project itself. It installs:
- `unstructured-inference` (wraps the layout detection)
- `onnxruntime` (runs the ONNX model — has native arm64 wheels)
- `pdf2image` (rasterizes PDF pages for layout analysis)
- `pytesseract` (OCR integration, uses the `tesseract` binary from brew)
- The detectron2_onnx model weights (downloaded on first use, ~200MB)
**First-run verification:**
 
Before committing to a full 261-PDF run, verify hi_res works on a single
known-good document:
 
```bash
python3 -c "
from unstructured.partition.pdf import partition_pdf
elements = partition_pdf(
    filename='data/computer-science-major.pdf',
    strategy='hi_res',
    infer_table_structure=True,
)
print(f'Extracted {len(elements)} elements')
print(f'Element types: {set(type(e).__name__ for e in elements)}')
"
```
 
Expected output:
- 15-40 elements per page for typical catalog PDFs
- Element types include `Title`, `NarrativeText`, `Table`, `ListItem`
- First run takes 30-60 seconds per page (model download + inference)
- Subsequent runs cache the model weights and run faster
If the first run fails with an `onnxruntime` error, install the
Apple Silicon-specific build:
 
```bash
pip install onnxruntime-silicon
```
 
**Alternative — `ocr_only` strategy for multi-column PDFs:**
 
The unstructured docs note that `hi_res` has difficulty ordering elements
for documents with multiple columns. Your 2025-2026 Academic Catalog is
heavily multi-column. If `hi_res` produces poor results on the catalog
specifically, consider running `ocr_only` as a fallback for just that
document:
 
```python
# For the catalog specifically if hi_res struggles
elements = partition_pdf(
    filename='data/2025-2026 Academic Catalog.pdf',
    strategy='ocr_only',
    languages=['eng'],
)
```
 
`ocr_only` runs Tesseract on rasterized page images and feeds raw text
through `partition_text`. Slower than `hi_res` but handles multi-column
layouts more reliably. Test on 5-10 pages of the catalog before deciding
which strategy to use for the full corpus.
 
### Step 2.2 — Update ingest.py for hi_res + larger chunks
 
Modify `load_pdfs()` in `ingest.py`:
 
```python
elements = partition_pdf(
    filename=str(p),
    strategy="hi_res",              # was "fast"
    infer_table_structure=True,
    include_page_breaks=True,
    languages=["eng"],              # explicit OCR language if fallback to OCR needed
)
 
chunks = chunk_by_title(
    elements,
    max_characters=3000,            # was 1500 — fits requirements tables
    new_after_n_chars=2500,         # was 1200
    combine_text_under_n_chars=300
)
```
 
Note: do NOT pass `hi_res_model_name` — that was an incorrect parameter
from an earlier version of this plan. `hi_res` uses `detectron2_onnx`
by default, which is what the `unstructured[local-inference]` install
provides.
 
Modify `chunk_parents()` in `ingest.py`:
 
```python
child_splitter = RecursiveCharacterTextSplitter(
    chunk_size=600,                 # was 300 — proportional to parent size
    chunk_overlap=60,               # was 30
    add_start_index=True,
)
```
 
**Optional per-document strategy override.** If `hi_res` struggles on the
multi-column academic catalog, add a strategy override in `load_pdfs()`:
 
```python
# Default strategy for most documents
strategy = "hi_res"
 
# Multi-column documents benefit from ocr_only per unstructured docs
if "Academic Catalog" in p.name or "catalog" in p.name.lower():
    strategy = "ocr_only"
    print(f"      INFO: Using ocr_only for multi-column doc {p.name}")
 
elements = partition_pdf(
    filename=str(p),
    strategy=strategy,
    infer_table_structure=True,
    include_page_breaks=True,
    languages=["eng"],
)
```
 
This gives you hi_res for well-formatted major/minor sheets and ocr_only
for the catalog. Test both approaches on 10 pages of the catalog and pick
whichever produces cleaner element boundaries.
 
### Step 2.3 — Clear existing state before re-ingestion
 
The chunking change means existing child IDs will no longer match
Pinecone records. Clear everything to get a clean baseline:
 
```bash
# Delete local artifacts
rm -rf ./store/parent_chunks/
rm ./store/bm25_encoder.json
rm ./store/ingestion_log.json
 
# Delete Pinecone index and recreate
# Use the Pinecone console or:
python3 -c "
from pinecone import Pinecone
import os
from dotenv import load_dotenv
load_dotenv()
pc = Pinecone(api_key=os.environ['PINECONE_API_KEY'])
pc.delete_index(os.environ['PINECONE_INDEX_NAME'])
print('Index deleted')
"
```
 
Then recreate the index in the Pinecone console with:
- metric: `dotproduct`
- dimension: 1024
- cloud: AWS, region: us-east-1
### Step 2.4 — Run hi_res ingestion
 
Expected runtime on M5 Pro for 261 PDFs with `hi_res` strategy:
2-4 hours depending on how many pages use the catalog (which is longer
than all other docs combined). First PDF triggers a ~200MB model download
to `~/.cache/unstructured/` — happens once.
 
Run in a terminal that won't timeout (use `caffeinate` to prevent sleep):
 
```bash
source .venv-ingest-macos/bin/activate
caffeinate -i python3 ingest.py 2>&1 | tee ingest_hires.log
```
 
Monitor the log for parse errors. `hi_res` occasionally fails on specific
PDFs with onnxruntime errors or layout detection issues — those files
get logged and skipped, which is expected and acceptable.
 
### Step 2.5 — Run verify_ingestion.py
 
After ingestion completes, run the existing verification suite:
 
```bash
python3 verify_ingestion.py
```
 
Expected changes vs. baseline:
- `total_parents` will be LOWER (fewer parents because each is larger)
- `total_children` will be LOWER (fewer children per parent)
- Vector count in Pinecone should match `total_children`
- BM25 vocabulary should be similar or slightly larger (better table extraction)
### Step 2.6 — Rerun RAGAS on new pipeline
 
Same procedure as Step 1.5 but output to `hires_` prefix:
 
```bash
# Start backend pointing at new index
uvicorn query:app --port 8002
 
# Run eval
python eval/run_eval.py --output hires
```
 
Output: `./eval/results/hires_YYYY-MM-DD.json`
 
### Step 2.7 — Compare baseline vs hires
 
Create `./eval/compare_runs.py`:
 
```python
# Load baseline_*.json and hires_*.json
# Print side-by-side table of all 4 metrics
# Print per-category deltas
# Print per-question regressions (questions that got worse)
# Generate matplotlib bar chart → eval/results/comparison.png
```
 
Write `./eval/results/phase2_analysis.md` covering:
 
1. Aggregate score deltas for all 4 metrics
2. Which categories improved most (expected: `requirement_list`)
3. Any regressions — questions that scored higher in baseline than hires
4. Decision: is the improvement sufficient, or proceed to Phase 3?
### Phase 2 decision criteria
 
Use these specific thresholds to decide on Phase 3:
 
| Context Recall improvement | Action |
|---|---|
| ≥ 0.15 absolute increase | Phase 2 is sufficient. Consider Phase 3 optional. |
| 0.05 to 0.15 increase | Borderline. Proceed to Phase 3 only if Faithfulness also improved. |
| < 0.05 increase | Phase 3 needed. Chunking wasn't the bottleneck; likely corpus coverage. |
| Decreased | Investigate before Phase 3. May need to tune hi_res parameters. |
 
### Phase 2 success criteria
 
- `hi_res` ingestion completed without fatal errors
- Verify script passes with new corpus
- RAGAS re-run produces `hires_*.json` results file
- Comparison script generates deltas and chart
- Phase 2 analysis markdown written with Phase 3 decision
---

## PHASE 3 — Agentic Web Search (CONDITIONAL)

### When to skip Phase 3

If Phase 2 Context Recall improved by ≥ 0.15 absolute, stop here.
Phase 3 adds significant complexity (latency, cost, error modes) that
only justifies its existence if the corpus-based system has a real ceiling.

### When to do Phase 3

If Phase 2 analysis shows the corpus genuinely lacks information students
need — e.g., current semester deadlines change, specific advisor policies
aren't published, waitlist rules vary by department — proceed.

### Step 3.1 — Choose web search provider

| Option | Cost | Latency | Quality |
|---|---|---|---|
| Tavily Search API | $0.005/query | ~1.5s | High, RAG-optimized |
| Brave Search API | $0.003/query | ~1.2s | Good |
| Exa API | $0.005/query | ~2s | Academic focus |

Recommend Tavily for academic policy use case. Free tier gives 1000
queries/month which is plenty for development.

### Step 3.2 — Add tool calling to query.py

Refactor `generate_answer()` to use Grok's function calling:

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_umd_web",
            "description": (
                "Search the UMD official websites (registrar.umd.edu, "
                "academiccatalog.umd.edu, undergrad.cs.umd.edu) for "
                "information not in the local knowledge base. Use only "
                "when the context documents explicitly lack the needed info."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    }
]
```

Implement `search_umd_web()` that:
1. Constrains results to UMD domains (Tavily supports `include_domains`)
2. Returns top 3 results as strings
3. Is called in a loop — model can call multiple times, up to 3 iterations
4. Each tool result gets appended as a `tool` role message
5. Model generates final answer after tool calls resolve

### Step 3.3 — Re-run RAGAS on agentic pipeline

```bash
python eval/run_eval.py --output agentic
```

### Step 3.4 — Three-way comparison

Compare baseline, hires, and agentic results. Expected pattern:
- Context Recall should increase further
- Faithfulness may decrease slightly (web content less reliable)
- Answer Relevancy should increase for previously-unanswerable questions
- Latency will increase 2-5x for queries that trigger tool calls

### Phase 3 analysis document

Write `./eval/results/phase3_analysis.md` with final three-way comparison,
cost analysis (Tavily cost per query × expected monthly volume), and
recommendation on whether to ship agentic to production.

---

## File deliverables summary

By end of plan execution, repo will contain:

```
ask-testudo/
├── query.py                            ← add /ask_with_contexts endpoint
├── ingest.py                           ← Phase 2: hi_res + larger chunks
└── eval/
    ├── golden_dataset.json             ← 60 QA pairs (Phase 1)
    ├── run_eval.py                     ← RAGAS runner
    ├── compare_runs.py                 ← side-by-side comparison
    ├── requirements_eval.txt
    └── results/
        ├── baseline_YYYY-MM-DD.json    ← Phase 1 output
        ├── baseline_analysis.md
        ├── hires_YYYY-MM-DD.json       ← Phase 2 output
        ├── phase2_analysis.md
        ├── comparison.png              ← bar chart
        ├── agentic_YYYY-MM-DD.json     ← Phase 3 output (if done)
        └── phase3_analysis.md
```

---

## DO NOT

- Do not skip Phase 1. The baseline is the foundation of every subsequent
  decision.
- Do not use Grok as the RAGAS judge LLM. An LLM evaluating itself produces
  inflated scores.
- Do not start Phase 3 automatically after Phase 2 — check the decision
  criteria first.
- Do not modify the golden dataset between runs. It must stay constant to
  produce comparable metrics.
- Do not re-use the existing venv for eval work. Keep `.venv-eval`,
  `.venv-query`, and `.venv-ingest-macos` separate to avoid dependency
  conflicts.
- Do not commit `.env` or API keys to the repo.
- Do not delete the baseline results when running hires. Keep all three
  generations of results files for the final comparison.
- Do not run eval against the production Railway backend — run against
  localhost with a development copy of the index, to avoid polluting
  production with evaluation queries.

---

## Success criteria for this plan

1. Phase 1 baseline metrics exist and are documented
2. Phase 2 improvements are quantified with specific numeric deltas
3. Phase 3 decision is made based on Phase 2 data, not intuition
4. All changes to ingest.py and query.py are incremental and reversible
5. Every result file is timestamped and stored in `./eval/results/`
