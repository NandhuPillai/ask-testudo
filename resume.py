"""
resume_from_step5.py

Run this when ingest.py crashed during step 5 (embedding) or step 6 (upsert).
It loads the already-saved artifacts from ./store/ and picks up from embedding.

Steps 1-4 are skipped entirely — artifacts are loaded from disk.
Steps 5-7 are re-run in full.

Since child IDs are deterministic UUIDs, any vectors already in Pinecone from
the crashed run will be safely overwritten with identical data.

Usage:
    python3 resume_from_step5.py
"""

import os
import sys
import json
import uuid
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

from dotenv import load_dotenv
from tqdm import tqdm

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_cohere import CohereEmbeddings
from pinecone import Pinecone
from pinecone_text.sparse import BM25Encoder


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def validate_environment():
    load_dotenv()
    missing = []
    for key in ["COHERE_API_KEY", "PINECONE_API_KEY", "PINECONE_INDEX_NAME"]:
        if not os.environ.get(key):
            missing.append(key)
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)


def validate_artifacts():
    """Ensure steps 1-4 artifacts exist before proceeding."""
    errors = []
    chunks_dir = Path("./store/parent_chunks/")
    bm25_path  = Path("./store/bm25_encoder.json")
    log_path   = Path("./store/ingestion_log.json")

    if not chunks_dir.is_dir() or not any(chunks_dir.iterdir()):
        errors.append("./store/parent_chunks/ is missing or empty — re-run ingest.py from scratch")
    if not bm25_path.is_file() or bm25_path.stat().st_size == 0:
        errors.append("./store/bm25_encoder.json is missing or empty — re-run ingest.py from scratch")
    if not log_path.is_file():
        errors.append("./store/ingestion_log.json is missing — re-run ingest.py from scratch")

    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Load saved artifacts from disk
# ---------------------------------------------------------------------------

def load_parents_from_store(store_path: str) -> List[Document]:
    """Reload all parent documents from LocalFileStore on disk."""
    parent_files = sorted(Path(store_path).rglob("*.json"))
    parent_docs  = []

    for p in tqdm(parent_files, desc="      Loading parents from disk"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            parent_docs.append(Document(
                page_content=data["page_content"],
                metadata=data["metadata"],
            ))
        except Exception as e:
            print(f"      WARNING: Could not load {p.name}: {e}")

    return parent_docs


def rechunk_parents(parent_docs: List[Document]) -> List[Document]:
    """
    Re-derive child chunks from loaded parents.
    RecursiveCharacterTextSplitter is instant — no API calls.
    UUIDs are deterministic so IDs are identical to the original run.
    """
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=30,
        add_start_index=True,
    )

    child_docs = []
    for parent in tqdm(parent_docs, desc="      Re-chunking parents"):
        # Reproduce the same stable UUID used in ingest.py
        parent_id_str = parent.metadata["source"] + parent.page_content[:64]
        parent_id     = str(uuid.uuid5(uuid.NAMESPACE_DNS, parent_id_str))

        # parent_id should already be in metadata from the saved file,
        # but recompute it anyway to ensure consistency
        parent.metadata["parent_id"] = parent_id

        try:
            children = child_splitter.split_documents([parent])
        except Exception as e:
            print(f"      WARNING: Splitter failed for '{parent.metadata['source']}': {e}")
            children = [Document(page_content=parent.page_content)]

        for child_index, child in enumerate(children):
            if not child.page_content or not child.page_content.strip():
                continue

            child_id = str(uuid.uuid5(
                uuid.NAMESPACE_DNS,
                parent_id + str(child_index)
            ))

            new_metadata                = parent.metadata.copy()
            new_metadata["child_id"]    = child_id
            new_metadata["chunk_index"] = child_index

            child_docs.append(Document(
                page_content=child.page_content.strip(),
                metadata=new_metadata,
            ))

    return child_docs


# ---------------------------------------------------------------------------
# Step 5 — Embed child chunks
# ---------------------------------------------------------------------------

def embed_children(
    child_docs: List[Document],
    bm25_encoder: BM25Encoder,
) -> List[Tuple[Document, List[float], Dict[str, Any]]]:
    embeddings = CohereEmbeddings(
        model="embed-english-v3.0",
        cohere_api_key=os.environ["COHERE_API_KEY"],
    )

    results    = []
    batch_size = 96
    batches    = [
        child_docs[i : i + batch_size]
        for i in range(0, len(child_docs), batch_size)
    ]

    print(f"      Total batches: {len(batches)}  "
          f"({len(child_docs)} chunks ÷ {batch_size} per batch)")

    for i, batch in enumerate(tqdm(batches, desc="      Embedding batches")):
        texts = [doc.page_content for doc in batch]

        # Retry loop with backoff — handles transient 429s even on paid tier
        max_retries = 5
        for attempt in range(max_retries):
            try:
                dense_vectors = embeddings.embed_documents(texts)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait = 10 * (attempt + 1)   # 10s, 20s, 30s, 40s, 50s
                print(f"\n      Batch {i+1} attempt {attempt+1} failed: {e}. "
                      f"Waiting {wait}s...")
                time.sleep(wait)

        sparse_vectors = [bm25_encoder.encode_documents([t])[0] for t in texts]

        for doc, dense_vec, sparse_vec in zip(batch, dense_vectors, sparse_vectors):
            results.append((doc, dense_vec, sparse_vec))

        # Throttle slightly between batches to stay comfortably under
        # Cohere's production rate limit (10M tokens/min).
        # Each batch ~96 chunks × ~300 chars ≈ ~6,000 tokens.
        # 76 batches × 6,000 = ~456,000 tokens total — well within limits.
        # The 0.1s pause just avoids burst spikes.
        time.sleep(0.1)

    return results


# ---------------------------------------------------------------------------
# Step 6 — Upsert to Pinecone
# ---------------------------------------------------------------------------

def upsert_to_pinecone(
    index,
    embedded_docs: List[Tuple[Document, List[float], Dict[str, Any]]],
):
    batch_size = 100
    batches    = [
        embedded_docs[i : i + batch_size]
        for i in range(0, len(embedded_docs), batch_size)
    ]

    for batch in tqdm(batches, desc="      Upserting batches"):
        vectors = []
        for doc, dense_vec, sparse_vec in batch:
            vectors.append({
                "id":            doc.metadata["child_id"],
                "values":        dense_vec,
                "sparse_values": sparse_vec,
                "metadata": {
                    "parent_id":   doc.metadata["parent_id"],
                    "source":      doc.metadata["source"],
                    "doc_type":    doc.metadata["doc_type"],
                    "page":        doc.metadata["page"],
                    "section":     doc.metadata["section"],
                    "file_hash":   doc.metadata["file_hash"],
                    "chunk_index": doc.metadata["chunk_index"],
                    "text":        doc.page_content[:500],
                },
            })

        max_retries = 3
        for attempt in range(max_retries):
            try:
                index.upsert(vectors=vectors)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                print(f"      Upsert attempt {attempt+1} failed: {e}. Retrying in 5s...")
                time.sleep(5)


# ---------------------------------------------------------------------------
# Step 7 — Update ingestion log
# ---------------------------------------------------------------------------

def update_log(child_docs: List[Document], index_name: str):
    log_path = Path("./store/ingestion_log.json")
    try:
        log_data = json.loads(log_path.read_text(encoding="utf-8"))
    except Exception:
        log_data = {}

    log_data["total_children"]   = len(child_docs)
    log_data["resume_timestamp"] = datetime.now(timezone.utc).isoformat()
    log_data["resume_completed"] = True

    log_path.write_text(
        json.dumps(log_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    start_time = time.time()

    print("=" * 60)
    print("  ask-testudo — resuming from step 5 (embedding)")
    print("=" * 60)

    validate_environment()
    validate_artifacts()

    # ── Connect to Pinecone ──────────────────────────────────────────────────
    print("\nConnecting to Pinecone...")
    pc         = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index_name = os.environ["PINECONE_INDEX_NAME"]
    index      = pc.Index(index_name)

    current_count = index.describe_index_stats().total_vector_count
    print(f"      Index '{index_name}' currently has {current_count} vectors.")
    print(f"      Any already-upserted vectors will be safely overwritten.")

    # ── Load saved parents ───────────────────────────────────────────────────
    print("\n[1/4] Loading parent documents from LocalFileStore...")
    parent_docs = load_parents_from_store("./store/parent_chunks/")
    print(f"      Loaded {len(parent_docs)} parent documents.")

    if not parent_docs:
        print("ERROR: No parent documents found. Re-run ingest.py from scratch.")
        sys.exit(1)

    # ── Re-derive children (instant) ────────────────────────────────────────
    print("\n[2/4] Re-chunking parents → children (instant, no API calls)...")
    child_docs = rechunk_parents(parent_docs)
    print(f"      Parents: {len(parent_docs)}  →  Children: {len(child_docs)}")

    if not child_docs:
        print("ERROR: Re-chunking produced zero children. Check parent store.")
        sys.exit(1)

    # ── Load BM25 encoder ────────────────────────────────────────────────────
    print("\n      Loading BM25 encoder from disk...")
    try:
        bm25_encoder = BM25Encoder().load("./store/bm25_encoder.json")
        print("      BM25 encoder loaded.")
    except Exception as e:
        print(f"ERROR: Could not load BM25 encoder: {e}")
        sys.exit(1)

    # ── [5/7] Embed ──────────────────────────────────────────────────────────
    print("\n[3/4] Embedding child chunks (Cohere embed-english-v3.0)...")
    embedded_docs = embed_children(child_docs, bm25_encoder)
    print(f"      Embedded {len(embedded_docs)} child chunks.")

    # ── [6/7] Upsert ─────────────────────────────────────────────────────────
    print("\n[4/4] Upserting to Pinecone...")
    upsert_to_pinecone(index, embedded_docs)
    final_count = index.describe_index_stats().total_vector_count
    print(f"      Index now contains {final_count} vectors.")

    # ── Update log ────────────────────────────────────────────────────────────
    update_log(child_docs, index_name)
    print("\n      Ingestion log updated → ./store/ingestion_log.json")

    elapsed    = time.time() - start_time
    mins, secs = divmod(int(elapsed), 60)
    print(f"\nDone. Resume complete in {mins}m {secs}s.")
    print(f"Run python3 verify_ingestion.py to confirm everything is correct.")


if __name__ == "__main__":
    main()