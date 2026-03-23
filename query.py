import os
import json
import time
import logging
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from pinecone import Pinecone
from pinecone_text.sparse import BM25Encoder
from langchain_cohere import CohereEmbeddings
from langchain_community.retrievers import PineconeHybridSearchRetriever
import cohere
from openai import OpenAI

from query_prompts import DECOMPOSE_PROMPT, SYSTEM_PROMPT, build_context_prompt

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CRAG_THRESHOLD = 0.30

FALLBACK_ANSWER = (
    "I don't have reliable information in my knowledge base to answer "
    "this confidently.\n\nFor accurate information I'd recommend:\n"
    "- UMD Registrar: registrar.umd.edu\n"
    "- Undergraduate catalog: academiccatalog.umd.edu\n"
    "- Your academic advisor\n"
    "- UMD helpdesk: help.umd.edu"
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("ask-testudo")

# ---------------------------------------------------------------------------
# Module-level shared resources (loaded once at startup)
# ---------------------------------------------------------------------------

pinecone_index = None
bm25_encoder = None
cohere_embeddings = None
retriever = None
cohere_client = None
xai_client = None
bm25_vocab_size = 0

# ---------------------------------------------------------------------------
# Startup / shutdown via lifespan
# ---------------------------------------------------------------------------

from contextlib import asynccontextmanager          # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pinecone_index, bm25_encoder, cohere_embeddings
    global retriever, cohere_client, xai_client, bm25_vocab_size

    load_dotenv()

    for key in ("COHERE_API_KEY", "PINECONE_API_KEY", "PINECONE_INDEX_NAME", "XAI_API_KEY"):
        if not os.environ.get(key):
            raise RuntimeError(f"Missing required environment variable: {key}")

    # ── BM25 encoder ──────────────────────────────────────────────────────
    try:
        bm25_encoder = BM25Encoder().load("./store/bm25_encoder.json")
        with open("./store/bm25_encoder.json", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for candidate in ("vocab", "doc_freq", "idf"):
                if candidate in raw and isinstance(raw[candidate], dict):
                    bm25_vocab_size = len(raw[candidate])
                    break
        log.info("[startup] %-35s OK (%d terms)", "loading BM25 encoder...", bm25_vocab_size)
    except Exception as exc:
        raise RuntimeError(f"Failed to load BM25 encoder: {exc}") from exc

    # ── Pinecone ──────────────────────────────────────────────────────────
    try:
        pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        pinecone_index = pc.Index(os.environ["PINECONE_INDEX_NAME"])
        idx_stats = pinecone_index.describe_index_stats()
        vector_count = idx_stats.total_vector_count
        log.info("[startup] %-35s OK (%d vectors)", "connecting to Pinecone...", vector_count)
    except Exception as exc:
        raise RuntimeError(f"Failed to connect to Pinecone: {exc}") from exc

    # ── Parent chunks store ───────────────────────────────────────────────
    parent_dir = Path("./store/parent_chunks")
    parent_file_count = len(list(parent_dir.glob("*.json"))) if parent_dir.exists() else 0
    log.info("[startup] %-35s OK (%d files)", "loading parent chunks store...", parent_file_count)

    # ── Cohere embedder ───────────────────────────────────────────────────
    try:
        cohere_embeddings = CohereEmbeddings(
            model="embed-english-v3.0",
            cohere_api_key=os.environ["COHERE_API_KEY"],
        )
        log.info("[startup] %-35s OK", "initialising Cohere embedder...")
    except Exception as exc:
        raise RuntimeError(f"Failed to initialise Cohere embeddings: {exc}") from exc

    # ── Hybrid retriever ──────────────────────────────────────────────────
    try:
        retriever = PineconeHybridSearchRetriever(
            embeddings=cohere_embeddings,
            sparse_encoder=bm25_encoder,
            index=pinecone_index,
            top_k=15,
            alpha=0.5,
            text_key="text",
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to initialise retriever: {exc}") from exc

    # ── Cohere rerank client ──────────────────────────────────────────────
    try:
        cohere_client = cohere.Client(api_key=os.environ["COHERE_API_KEY"])
    except Exception as exc:
        raise RuntimeError(f"Failed to initialise Cohere client: {exc}") from exc

    # ── xAI (Grok) client ────────────────────────────────────────────────
    try:
        xai_client = OpenAI(
            base_url="https://api.x.ai/v1",
            api_key=os.environ["XAI_API_KEY"],
        )
        log.info("[startup] %-35s OK", "initialising xAI client...")
    except Exception as exc:
        raise RuntimeError(f"Failed to initialise xAI client: {exc}") from exc

    log.info("\nask-testudo query pipeline ready.")

    yield  # application runs

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="ask-testudo", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://ask-testudo.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class Message(BaseModel):
    role: str       # "user" or "assistant"
    content: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    stream: bool = False
    history: list[Message] = []


# ---------------------------------------------------------------------------
# STEP 1 — decompose_query
# ---------------------------------------------------------------------------


def decompose_query(question: str) -> dict:
    try:
        response = xai_client.chat.completions.create(
            model="grok-4-1-fast-non-reasoning",
            messages=[
                {"role": "system", "content": DECOMPOSE_PROMPT},
                {"role": "user", "content": question},
            ],
            max_tokens=300,
            temperature=0.0,
        )

        text = response.choices[0].message.content.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        parsed = json.loads(text)

        if "sub_queries" not in parsed or "hyde_document" not in parsed:
            raise ValueError("Missing required fields in decomposition response")

        return parsed

    except Exception as exc:
        log.warning("[query] decompose failed (%s), falling back to raw question", exc)
        return {"sub_queries": [question], "hyde_document": question}


# ---------------------------------------------------------------------------
# STEP 2 — retrieve_chunks
# ---------------------------------------------------------------------------


def retrieve_chunks(sub_queries: list[str], hyde_document: str) -> list:
    all_queries = sub_queries + [hyde_document]
    seen: dict[str, object] = {}

    for query_str in all_queries:
        docs = retriever.invoke(query_str)
        for doc in docs:
            parent_id = doc.metadata.get("parent_id")
            chunk_index = int(doc.metadata.get("chunk_index", 0))
            child_id = f"{parent_id}_{chunk_index}" if parent_id else None
            if child_id and child_id not in seen:
                seen[child_id] = doc

    return list(seen.values())[:10]


# ---------------------------------------------------------------------------
# STEP 3 — swap_to_parents
# ---------------------------------------------------------------------------


def swap_to_parents(child_docs: list) -> list[dict]:
    seen_parent_ids: set[str] = set()
    parents: list[dict] = []

    for doc in child_docs:
        parent_id = doc.metadata.get("parent_id")
        if not parent_id or parent_id in seen_parent_ids:
            continue

        path = Path(f"./store/parent_chunks/{parent_id}.json")
        if not path.exists():
            log.warning("[query] parent file missing: %s", path)
            continue

        try:
            parent = json.loads(path.read_text(encoding="utf-8"))
            parents.append(parent)
            seen_parent_ids.add(parent_id)
        except Exception as exc:
            log.warning("[query] failed to read parent %s: %s", parent_id, exc)

    return parents


# ---------------------------------------------------------------------------
# STEP 4 — rerank_parents
# ---------------------------------------------------------------------------


def rerank_parents(parents: list[dict], question: str) -> tuple[list[dict], float]:
    if not parents:
        return [], 0.0

    result = cohere_client.rerank(
        query=question,
        documents=[p["page_content"] for p in parents],
        model="rerank-v3.5",
        top_n=min(8, len(parents)),
    )

    reordered = [parents[r.index] for r in result.results]
    top_score = result.results[0].relevance_score

    return reordered, float(top_score)


# ---------------------------------------------------------------------------
# STEP 6 — generate_answer
# ---------------------------------------------------------------------------


def generate_answer(parents: list[dict], question: str, history: list = []) -> str:
    history_messages = [
        {"role": m.role, "content": m.content}
        for m in history[-6:]    # last 3 turns (6 messages) max
    ]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history_messages,
        {"role": "user", "content": build_context_prompt(parents, question)},
    ]
    stream = xai_client.chat.completions.create(
        model="grok-4-1-fast-non-reasoning",
        messages=messages,
        max_tokens=1500,
        temperature=0.1,
        stream=True,
    )

    chunks: list[str] = []
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            chunks.append(delta)

    return "".join(chunks)


# ---------------------------------------------------------------------------
# STEP 7 — format_response
# ---------------------------------------------------------------------------


def _extract_sources(parents: list[dict]) -> list[dict]:
    sources: list[dict] = []
    seen: set[tuple[str, int]] = set()

    for parent in parents:
        meta = parent.get("metadata", {})
        filename = os.path.basename(meta.get("source", ""))
        page = int(meta.get("page", 0) or 0)
        key = (filename, page)
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            "filename": filename,
            "page": page,
            "section": meta.get("section", "") or "",
            "doc_type": meta.get("doc_type", "pdf"),
        })

    return sources


def _confidence_label(score: float) -> str:
    if score >= 0.50:
        return "high"
    if score >= 0.30:
        return "medium"
    return "low"


def format_response(answer: str, parents: list[dict], top_score: float) -> dict:
    return {
        "answer": answer,
        "sources": _extract_sources(parents),
        "confidence": _confidence_label(top_score),
        "rerank_score": round(top_score, 4),
        "fallback": False,
    }


# ---------------------------------------------------------------------------
# SSE streaming helpers
# ---------------------------------------------------------------------------


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _stream_answer(parents: list[dict], question: str, top_score: float):
    """Generator that yields SSE events for the streamed answer."""
    try:
        stream = xai_client.chat.completions.create(
            model="grok-4-1-fast-non-reasoning",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_context_prompt(parents, question)},
            ],
            max_tokens=800,
            temperature=0.1,
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield _sse_event({"type": "chunk", "content": delta})

    except Exception as exc:
        log.error("[query] streaming generation failed: %s", exc)
        yield _sse_event({"type": "error", "detail": str(exc)})
        return

    done_payload = {
        "type": "done",
        "sources": _extract_sources(parents),
        "confidence": _confidence_label(top_score),
        "rerank_score": round(top_score, 4),
    }
    yield _sse_event(done_payload)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/ask")
def ask(req: AskRequest):
    t_start = time.time()
    question = req.question

    # ── Step 1: decompose ─────────────────────────────────────────────────
    decomposition = decompose_query(question)
    sub_queries = decomposition["sub_queries"]
    hyde_document = decomposition["hyde_document"]
    log.info('[query] "%s" \u2192 %d sub-queries', question[:100], len(sub_queries))

    # ── Step 2: retrieve ──────────────────────────────────────────────────
    try:
        child_docs = retrieve_chunks(sub_queries, hyde_document)
    except Exception as exc:
        log.error("[query] retrieval failed: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "retrieval failed", "detail": str(exc)},
        )

    # ── Step 3: swap to parents ───────────────────────────────────────────
    try:
        parents = swap_to_parents(child_docs)
        if not parents:
            return JSONResponse(
                status_code=500,
                content={"error": "parent swap failed", "detail": "no parent documents found after swap"},
            )
    except Exception as exc:
        log.error("[query] parent swap failed: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "parent swap failed", "detail": str(exc)},
        )

    log.info(
        "[query] retrieved %d children \u2192 %d unique parents",
        len(child_docs), len(parents),
    )

    # ── Step 4: rerank ────────────────────────────────────────────────────
    try:
        reranked_parents, top_score = rerank_parents(parents, question)
    except Exception as exc:
        log.error("[query] reranking failed: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "reranking failed", "detail": str(exc)},
        )

    confidence = _confidence_label(top_score)
    log.info(
        "[query] reranked \u2192 top score %.4f \u2192 confidence: %s",
        top_score, confidence,
    )

    # ── Step 5: CRAG threshold ────────────────────────────────────────────
    if top_score < CRAG_THRESHOLD:
        elapsed = time.time() - t_start
        log.info("[query] fallback in %.1fs", elapsed)

        fallback = {
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "confidence": "low",
            "rerank_score": round(top_score, 4),
            "fallback": True,
        }

        if req.stream:
            return StreamingResponse(
                iter([_sse_event({"type": "done", **fallback})]),
                media_type="text/event-stream",
            )
        return fallback

    # ── Streaming path ────────────────────────────────────────────────────
    if req.stream:
        return StreamingResponse(
            _stream_answer(reranked_parents, question, top_score),
            media_type="text/event-stream",
        )

    # ── Step 6: generate (non-streaming) ──────────────────────────────────
    try:
        answer = generate_answer(reranked_parents, question, req.history)
    except Exception as exc:
        log.error("[query] generation failed: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "generation failed", "detail": str(exc)},
        )

    # ── Step 7: format ────────────────────────────────────────────────────
    response = format_response(answer, reranked_parents, top_score)

    elapsed = time.time() - t_start
    log.info("[query] answered in %.1fs", elapsed)

    return response


@app.get("/health")
def health():
    try:
        idx_stats = pinecone_index.describe_index_stats()
        vector_count = idx_stats.total_vector_count
    except Exception:
        vector_count = -1

    parent_dir = Path("./store/parent_chunks")
    parent_count = len(list(parent_dir.glob("*.json"))) if parent_dir.exists() else 0

    return {
        "status": "ok",
        "index_vector_count": vector_count,
        "parent_chunks_on_disk": parent_count,
        "bm25_vocabulary_size": bm25_vocab_size,
    }


@app.get("/ping")
def ping():
    return {"status": "warm"}


@app.get("/")
def root():
    return {
        "name": "ask-testudo",
        "version": "1.0.0",
        "description": "UMD academic policy assistant",
        "endpoints": ["/ask", "/health", "/ping"],
    }
