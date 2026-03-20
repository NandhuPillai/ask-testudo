import os
import sys
import json
import uuid
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

from dotenv import load_dotenv
from tqdm import tqdm

from unstructured.partition.pdf import partition_pdf
from unstructured.chunking.title import chunk_by_title
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_cohere import CohereEmbeddings

from pinecone import Pinecone
from pinecone_text.sparse import BM25Encoder


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def get_file_hash(filepath: str) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()[:12]


# ---------------------------------------------------------------------------
# Step 0 — Validate environment & Pinecone setup
# ---------------------------------------------------------------------------

def validate_environment():
    load_dotenv()
    missing = []
    for key in ["COHERE_API_KEY", "PINECONE_API_KEY", "PINECONE_INDEX_NAME"]:
        if not os.environ.get(key):
            missing.append(key)

    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        print("Make sure these are set in your .env file at the repo root.")
        sys.exit(1)


def setup_pinecone() -> Any:
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index_name = os.environ["PINECONE_INDEX_NAME"]

    index_info = pc.describe_index(index_name)
    if index_info.metric != "dotproduct":
        print(
            f"ERROR: Pinecone index '{index_name}' uses metric "
            f"'{index_info.metric}' instead of 'dotproduct'.\n"
            f"Hybrid sparse-dense search requires dotproduct.\n"
            f"Please delete the index in the Pinecone console and re-run ingest.py."
        )
        sys.exit(1)
    print(f"      Connected to existing index '{index_name}' (dotproduct).")

    return pc.Index(index_name)


# ---------------------------------------------------------------------------
# Step 1 — Load & parse PDF documents
# ---------------------------------------------------------------------------

def load_pdfs(data_dir: str) -> Tuple[List[Document], Dict[str, Any]]:
    docs = []
    stats = {}
    path = Path(data_dir)

    if not path.exists():
        return docs, stats

    pdf_files = sorted(path.rglob("*.pdf"))
    if not pdf_files:
        return docs, stats

    for p in pdf_files:
        if p.stat().st_size == 0:
            print(f"      WARNING: Skipping empty file {p}")
            continue

        rel_path = str(p.relative_to(Path(".")))
        file_hash = get_file_hash(str(p))

        try:
            elements = partition_pdf(
                filename=str(p),
                strategy="fast",
                infer_table_structure=True,
                include_page_breaks=True
            )
            chunks = chunk_by_title(
                elements,
                max_characters=1500,
                new_after_n_chars=1200,
                combine_text_under_n_chars=200
            )

            p_docs = []
            for chunk in chunks:
                text = chunk.text if hasattr(chunk, "text") else str(chunk)
                if not text or not text.strip():
                    continue

                metadata = getattr(chunk, "metadata", None)
                page     = getattr(metadata, "page_number", None) if metadata else None
                section  = getattr(metadata, "section", None) if metadata else None

                p_docs.append(Document(
                    page_content=text.strip(),
                    metadata={
                        "source":    rel_path,
                        "doc_type":  "pdf",
                        "page":      page if page is not None else 0,
                        "section":   section if section is not None else "",
                        "file_hash": file_hash,
                    }
                ))

            docs.extend(p_docs)
            stats[rel_path] = {
                "parent_count": len(p_docs),
                "error":        None,
                "file_hash":    file_hash,
            }

        except Exception as e:
            print(f"      ERROR parsing {p}: {e}")
            stats[rel_path] = {
                "parent_count": 0,
                "error":        str(e),
                "file_hash":    file_hash,
            }

    return docs, stats


# ---------------------------------------------------------------------------
# load_markdowns() preserved here for future use if markdown sources
# with real content are added to ./docs. Not called by main() currently.
# To re-enable: add md_docs, md_stats = load_markdowns("./docs") in main()
# and merge: all_parents = pdf_docs + md_docs
# ---------------------------------------------------------------------------

def load_markdowns(docs_dir: str) -> Tuple[List[Document], Dict[str, Any]]:
    from langchain_community.document_loaders import UnstructuredMarkdownLoader
    docs = []
    stats = {}
    path = Path(docs_dir)

    if not path.exists():
        return docs, stats

    md_files = sorted(path.rglob("*.md"))
    if not md_files:
        return docs, stats

    for p in md_files:
        if p.stat().st_size == 0:
            print(f"      WARNING: Skipping empty file {p}")
            continue

        rel_path = str(p.relative_to(Path(".")))
        file_hash = get_file_hash(str(p))

        try:
            loader = UnstructuredMarkdownLoader(str(p), mode="elements")
            loaded_docs = loader.load()

            p_docs = []
            for doc in loaded_docs:
                if not doc.page_content or not doc.page_content.strip():
                    continue

                section = (
                    doc.metadata.get("category", "")
                    or doc.metadata.get("section", "")
                )

                p_docs.append(Document(
                    page_content=doc.page_content.strip(),
                    metadata={
                        "source":    rel_path,
                        "doc_type":  "markdown",
                        "page":      0,
                        "section":   section,
                        "file_hash": file_hash,
                    }
                ))

            docs.extend(p_docs)
            stats[rel_path] = {
                "parent_count": len(p_docs),
                "error":        None,
                "file_hash":    file_hash,
            }

        except Exception as e:
            print(f"      ERROR parsing {p}: {e}")
            stats[rel_path] = {
                "parent_count": 0,
                "error":        str(e),
                "file_hash":    file_hash,
            }

    return docs, stats


# ---------------------------------------------------------------------------
# Step 2 — Split parent chunks into child chunks
#
# RecursiveCharacterTextSplitter: no API calls, instant, battle-tested.
# Parents (~1500 chars from unstructured) are split into children (~300 chars)
# with 30-char overlap to avoid cutting sentences at boundaries.
# Parents are stored in full for context delivery; only children are indexed.
# ---------------------------------------------------------------------------

def chunk_parents(parent_docs: List[Document]) -> List[Document]:
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=30,
        add_start_index=True,
    )

    child_docs = []
    for parent in tqdm(parent_docs, desc="      Chunking parents"):
        # Stable UUID — same source + content prefix always yields same parent_id.
        # Re-ingestion of unchanged files produces identical IDs, no duplicates.
        parent_id_str = parent.metadata["source"] + parent.page_content[:64]
        parent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, parent_id_str))
        parent.metadata["parent_id"] = parent_id

        try:
            children = child_splitter.split_documents([parent])
        except Exception as e:
            print(
                f"      WARNING: Splitter failed for a doc in "
                f"'{parent.metadata['source']}': {e}. Using parent as single chunk."
            )
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
# Step 3 — Store parent chunks to disk (LocalFileStore pattern)
# ---------------------------------------------------------------------------

def store_parents(parent_docs: List[Document], store_path: str):
    Path(store_path).mkdir(parents=True, exist_ok=True)

    for doc in parent_docs:
        val = json.dumps(
            {
                "page_content": doc.page_content,
                "metadata":     doc.metadata,
            },
            indent=2,
            ensure_ascii=False,
        )
        file_path = Path(store_path) / f"{doc.metadata['parent_id']}.json"
        file_path.write_text(val, encoding="utf-8")


# ---------------------------------------------------------------------------
# Step 4 — Fit and persist BM25 encoder
# ---------------------------------------------------------------------------

def fit_bm25(child_docs: List[Document], save_path: str) -> BM25Encoder:
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)

    corpus = [doc.page_content for doc in child_docs]
    bm25_encoder = BM25Encoder()
    bm25_encoder.fit(corpus)
    bm25_encoder.dump(save_path)
    return bm25_encoder


# ---------------------------------------------------------------------------
# Step 5 — Embed child chunks (dense + sparse)
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
    batch_size = 96  # Cohere's max batch size for embed-english-v3.0
    batches    = [
        child_docs[i : i + batch_size]
        for i in range(0, len(child_docs), batch_size)
    ]

    for batch in tqdm(batches, desc="      Embedding batches"):
        texts = [doc.page_content for doc in batch]

        dense_vectors  = embeddings.embed_documents(texts)
        sparse_vectors = [bm25_encoder.encode_documents([t])[0] for t in texts]

        for doc, dense_vec, sparse_vec in zip(batch, dense_vectors, sparse_vectors):
            results.append((doc, dense_vec, sparse_vec))

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
                    # Truncated copy stored in Pinecone for console debugging
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
                print(f"      Upsert attempt {attempt + 1} failed: {e}. Retrying in 5s...")
                time.sleep(5)


# ---------------------------------------------------------------------------
# Step 7 — Write ingestion log
# ---------------------------------------------------------------------------

def write_log(
    stats: Dict[str, Any],
    child_docs: List[Document],
    index_name: str,
    log_path: str,
):
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    total_parents = sum(s["parent_count"] for s in stats.values())

    child_counts: Dict[str, int] = {rel_path: 0 for rel_path in stats}
    for doc in child_docs:
        src = doc.metadata["source"]
        if src in child_counts:
            child_counts[src] += 1

    files_list = []
    for rel_path in sorted(stats.keys()):
        s = stats[rel_path]
        rec = {
            "path":         rel_path,
            "doc_type":     "pdf" if rel_path.endswith(".pdf") else "markdown",
            "file_hash":    s["file_hash"],
            "parent_count": s["parent_count"],
            "child_count":  child_counts.get(rel_path, 0),
        }
        if s["error"]:
            rec["parse_error"] = s["error"]
        files_list.append(rec)

    log_data = {
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "total_files":     len(stats),
        "total_parents":   total_parents,
        "total_children":  len(child_docs),
        "pinecone_index":  index_name,
        "embedding_model": "embed-english-v3.0",
        "files":           files_list,
    }

    Path(log_path).write_text(
        json.dumps(log_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    start_time = time.time()

    validate_environment()

    if not Path("./data").exists():
        print("ERROR: ./data/ directory not found. Nothing to ingest.")
        sys.exit(1)

    print("\nConnecting to Pinecone...")
    index = setup_pinecone()

    # ── [1/7] Load ───────────────────────────────────────────────────────────
    print("\n[1/7] Loading documents...")
    pdf_docs, pdf_stats = load_pdfs("./data")

    all_parents = pdf_docs
    all_stats   = pdf_stats

    error_count = sum(1 for s in all_stats.values() if s.get("error"))
    print(f"      PDF files found:  {len(pdf_stats)}")
    print(f"      Parse errors:     {error_count}")
    print(f"      Total parents:    {len(all_parents)}")

    if not all_parents:
        print("ERROR: No documents loaded. Check ./data/ contents.")
        sys.exit(1)

    # ── [2/7] Chunk ──────────────────────────────────────────────────────────
    print("\n[2/7] Chunking parents → children...")
    child_docs = chunk_parents(all_parents)
    print(f"      Parents: {len(all_parents)}  →  Children: {len(child_docs)}")

    if not child_docs:
        print("ERROR: Chunking produced zero child documents. Aborting.")
        sys.exit(1)

    # ── [3/7] Store parents ──────────────────────────────────────────────────
    print("\n[3/7] Storing parent chunks to LocalFileStore...")
    store_parents(all_parents, "./store/parent_chunks/")
    print(f"      Stored {len(all_parents)} parent documents.")

    # ── [4/7] BM25 ──────────────────────────────────────────────────────────
    print("\n[4/7] Fitting BM25 encoder...")
    bm25_encoder = fit_bm25(child_docs, "./store/bm25_encoder.json")
    print(f"      BM25 encoder fitted on {len(child_docs)} child documents and saved.")

    # ── [5/7] Embed ──────────────────────────────────────────────────────────
    print("\n[5/7] Embedding child chunks (Cohere embed-english-v3.0)...")
    embedded_docs = embed_children(child_docs, bm25_encoder)
    print(f"      Embedded {len(embedded_docs)} child chunks.")

    # ── [6/7] Upsert ─────────────────────────────────────────────────────────
    print("\n[6/7] Upserting to Pinecone (dotproduct index)...")
    upsert_to_pinecone(index, embedded_docs)
    index_stats = index.describe_index_stats()
    print(f"      Index now contains {index_stats.total_vector_count} vectors.")

    # ── [7/7] Log ────────────────────────────────────────────────────────────
    print("\n[7/7] Writing ingestion log → ./store/ingestion_log.json")
    write_log(
        all_stats,
        child_docs,
        os.environ["PINECONE_INDEX_NAME"],
        "./store/ingestion_log.json",
    )

    elapsed    = time.time() - start_time
    mins, secs = divmod(int(elapsed), 60)
    print(f"\nDone. Ingestion complete in {mins}m {secs}s.")


if __name__ == "__main__":
    main()