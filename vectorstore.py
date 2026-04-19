import os
import time
from typing import List, Tuple, Dict, Any

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import chromadb
import chromadb.errors as chroma_errors


load_dotenv()

MODEL_NAME = os.getenv("SENTENCE_TRANSFORMER_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "my_documents")

tenant = os.getenv("TENANT", "").strip()
database = os.getenv("DATABASE", "").strip()
api_key = os.getenv("CHROMA_API_KEY", "").strip()

DEFAULT_MAX_BYTES = int(os.getenv("CHROMA_MAX_BYTES", "15000"))
MIN_MAX_BYTES = 2000
MAX_RETRIES = 5

_embedder = SentenceTransformer(MODEL_NAME)

if tenant and database and api_key:
    client = chromadb.CloudClient(
        tenant=tenant,
        database=database,
        api_key=api_key,
    )
else:
    raise RuntimeError("Missing Chroma cloud credentials (TENANT, DATABASE, CHROMA_API_KEY)")

collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"description": "Document embeddings with SentenceTransformers"},
)


def _split_text_by_bytes(text: str, max_bytes: int = DEFAULT_MAX_BYTES) -> List[str]:
    if not text:
        return []
    words = text.split()
    chunks = []
    cur_words = []
    cur_bytes = 0
    for w in words:
        w_bytes = len((w + " ").encode("utf-8"))
        if cur_words and (cur_bytes + w_bytes > max_bytes):
            chunks.append(" ".join(cur_words).strip())
            cur_words = [w]
            cur_bytes = w_bytes
        else:
            cur_words.append(w)
            cur_bytes += w_bytes
    if cur_words:
        chunks.append(" ".join(cur_words).strip())
    return [c for c in chunks if c]


def _embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    embs = _embedder.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return [e.tolist() for e in embs]


def _delete_existing_docid(doc_id: str) -> None:
    try:
        collection.delete(where={"doc_id": doc_id})
    except Exception:
        pass


def add_to_index(text_chunks: List[str], doc_id: str, upsert: bool = True) -> Dict[str, Any]:
    if isinstance(text_chunks, str):
        text_chunks = [text_chunks]
    if upsert:
        _delete_existing_docid(doc_id)

    max_bytes = DEFAULT_MAX_BYTES
    attempts = 0

    def prepare_safe_chunks(chunks: List[str], mb: int) -> List[str]:
        safe = []
        for t in chunks:
            if t:
                safe.extend(_split_text_by_bytes(t, max_bytes=mb))
        return safe

    last_exception = None
    while attempts < MAX_RETRIES and max_bytes >= MIN_MAX_BYTES:
        attempts += 1
        safe_chunks = prepare_safe_chunks(text_chunks, max_bytes)
        if not safe_chunks:
            return {"added": 0, "attempts": attempts, "used_max_bytes": max_bytes}

        try:
            batch_size = 1000
            try:
                batch_size = collection.get_max_batch_size()
            except Exception:
                # fallback to a sensible default if method not available
                batch_size = 1000

            total_added = 0
            # add in batches
            for start in range(0, len(safe_chunks), batch_size):
                batch = safe_chunks[start:start + batch_size]
                ids = [f"{doc_id}_{start + i}" for i in range(len(batch))]
                metadatas = [{"doc_id": doc_id, "chunk_index": start + i} for i in range(len(batch))]
                embeddings = _embed_texts(batch)
                collection.add(
                    ids=ids,
                    documents=batch,
                    metadatas=metadatas,
                    embeddings=embeddings,
                )
                total_added += len(batch)

            return {"added": total_added, "attempts": attempts, "used_max_bytes": max_bytes, "batches": (len(safe_chunks) + batch_size - 1) // batch_size}

        except Exception as e:
            last_exception = e
            err_str = str(e)

            is_chroma_quota = False
            try:
                if isinstance(e, chroma_errors.ChromaError):
                    is_chroma_quota = True
            except Exception:
                pass

            if ("Quota exceeded" in err_str) or ("Document size" in err_str) or is_chroma_quota:
                new_max = max(max_bytes // 2, MIN_MAX_BYTES)
                if new_max >= max_bytes:
                    break
                max_bytes = new_max
                time.sleep(0.5)
                continue
            else:
                raise

    if last_exception:
        raise last_exception
    raise RuntimeError(f"Failed to add document {doc_id}")


def search_index(query: str, top_k: int = 3) -> List[Tuple[str, str, float]]:
    if not query:
        return []
    q_emb = _embed_texts([query])[0]
    try:
        results = collection.query(
            query_embeddings=[q_emb],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    out = []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        dist = dists[i] if i < len(dists) else None
        doc_id = meta.get("doc_id")
        out.append((doc_id, doc, float(dist) if dist is not None else None))
    return out
