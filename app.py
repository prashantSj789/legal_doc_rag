
from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv
import docx
from langchain_google_genai import ChatGoogleGenerativeAI
from vectorstore import add_to_index, search_index
from PyPDF2 import PdfReader
import redis
import graphstore   
import spacy

load_dotenv()

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Gemini / LangChain LLM init
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.0"))

llm = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    temperature=GEMINI_TEMPERATURE,
    max_retries=2,
)

# Redis setup
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Configuration: keep last N messages per session
CONTEXT_WINDOW = int(os.getenv("SESSION_CONTEXT_WINDOW", "10"))  # now 10 by default
MAX_PROMPT_CHUNKS = int(os.getenv("MAX_PROMPT_CHUNKS", "6"))

# Initialize graph constraints/indexes (idempotent)
try:
    graphstore.create_constraints_and_indexes()
except Exception:
    app.logger.warning("Could not create indexes/constraints on Neo4j - continuing without failing.")

# spaCy NLP model (NER)
try:
    nlp = spacy.load("en_core_web_sm")
except Exception as e:
    # user should run: python -m spacy download en_core_web_sm
    raise RuntimeError("spaCy model 'en_core_web_sm' not found. Run inside your venv: python -m spacy download en_core_web_sm") from e


# -------------------------
# Utilities for files + text
# -------------------------

def extract_text(file_path):
    """Extract raw text from PDF, DOCX, or TXT (case-insensitive)"""
    text = ""
    lower = file_path.lower()
    try:
        if lower.endswith(".pdf"):
            reader = PdfReader(file_path)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        elif lower.endswith(".docx"):
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                if para.text:
                    text += para.text + "\n"
        elif lower.endswith(".txt"):
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        else:
            # fallback: read as text
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
    except Exception as e:
        app.logger.exception(f"Error extracting text from {file_path}: {e}")
    return text


def chunk_text(text, chunk_size=2000, overlap=200):
    """Split text into larger overlapping chunks (fewer records in Chroma)"""
    if not text:
        return []
    words = text.split()
    chunks = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
    return chunks


# -------------------------
# Redis session helpers
# -------------------------

def session_messages_key(session_id: str) -> str:
    return f"session:{session_id}:messages"


def _now_iso():
    return datetime.utcnow().isoformat() + "Z"


def store_message(session_id: str, role: str, text: str):
    """Append a message to the session list in Redis and trim to CONTEXT_WINDOW."""
    if not session_id:
        return
    key = session_messages_key(session_id)
    msg = {"role": role, "text": text, "ts": _now_iso()}
    try:
        redis_client.rpush(key, json.dumps(msg))
        redis_client.ltrim(key, -CONTEXT_WINDOW, -1)
    except Exception:
        app.logger.exception("Failed to write/trim Redis session list")


def get_session_history(session_id: str, limit: int = None):
    """Return list of messages (oldest -> newest)."""
    if not session_id:
        return []
    key = session_messages_key(session_id)
    try:
        raw = redis_client.lrange(key, 0, -1)
    except Exception:
        app.logger.exception("Failed to read session history from Redis")
        return []
    msgs = []
    for item in raw:
        try:
            msgs.append(json.loads(item))
        except Exception:
            msgs.append({"role": "human", "text": item, "ts": None})
    if limit:
        return msgs[-limit:]
    return msgs


def clear_session(session_id: str):
    if not session_id:
        return
    key = session_messages_key(session_id)
    try:
        redis_client.delete(key)
    except Exception:
        app.logger.exception("Failed to delete session key from Redis")


# -------------------------
# Endpoints
# -------------------------

@app.route('/upload', methods=["POST"])
def upload_doc():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    doc_id = file.filename

    # Save temporarily
    file_path = os.path.join(UPLOAD_FOLDER, doc_id)
    file.save(file_path)

    try:
        text = extract_text(file_path)
    finally:
        # Always remove the temp file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            app.logger.exception("Failed to remove temp file")

    chunks = chunk_text(text)
    if not chunks:
        return jsonify({"error": "No text extracted from document"}), 400

    # 1) Add to Chroma (vector store)
    try:
        add_to_index(chunks, doc_id)
    except Exception:
        app.logger.exception("add_to_index failed")

    # 2) Persist in Neo4j: Document -> Chunk nodes, and create Entity mentions
    try:
        graphstore.create_document(doc_id, title=doc_id, source_url=None, doc_type="uploaded")
        for idx, c in enumerate(chunks):
            preview = c[:1200]
            try:
                chunk_node_id = graphstore.create_chunk(doc_id, idx, preview, chroma_id=None)
            except Exception:
                chunk_node_id = f"{doc_id}::chunk::{idx}"
            # run spaCy NER on preview
            try:
                doc_sp = nlp(preview)
                seen = set()
                for ent in doc_sp.ents:
                    name = ent.text.strip()
                    if len(name) < 3:
                        continue
                    if name in seen:
                        continue
                    seen.add(name)
                    try:
                        graphstore.create_entity(name, ent.label_)
                        graphstore.link_chunk_entity(chunk_node_id, name)
                    except Exception:
                        app.logger.exception("Failed to create/link entity in graph")
            except Exception:
                app.logger.exception("spaCy NER failed on chunk preview")
    except Exception:
        app.logger.exception("Neo4j ingestion failed (continuing)")

    return jsonify({
        "message": "Document indexed successfully",
        "doc_id": doc_id,
        "chunks": len(chunks)
    }), 201


@app.route('/create_session', methods=['GET'])
def create_session():
    """Create a new session and return its session_id."""
    session_id = str(uuid.uuid4())
    return jsonify({"session_id": session_id}), 200


@app.route('/query', methods=['POST'])
def query():
    """Single endpoint that accepts optional session_id in payload.

    Behavior:
      - If session_id provided: fetch last CONTEXT_WINDOW messages and include them when calling LLM.
      - Store the user's query message into Redis (as 'human') and also create a Message node in Neo4j.
      - After LLM reply, store assistant reply into Redis (as 'assistant') and create a Message node, plus link to used chunks if present.
      - Redis list always trimmed to last CONTEXT_WINDOW messages.
    """
    payload = request.get_json(silent=True) or {}
    query_text = payload.get("query") or request.form.get("query")
    if not query_text:
        return jsonify({"error": "Missing 'query' in JSON body or form data"}), 400

    session_id = payload.get("session_id")  # optional

    try:
        top_k = int(payload.get("top_k", 3))
    except Exception:
        top_k = 3

    # If session provided, store the incoming user message in Redis and create a message node in graph
    msg_node_id = None
    if session_id:
        try:
            store_message(session_id, "human", query_text)
        except Exception:
            app.logger.exception("Failed to store user message in Redis")
        try:
            msg_node_id = str(uuid.uuid4())
            graphstore.store_message(session_id, msg_node_id, "human", query_text)
        except Exception:
            app.logger.exception("Failed to store user message node in Neo4j")
            msg_node_id = None

    # Retrieval from vectorstore
    try:
        results = search_index(query_text, top_k=top_k)
    except Exception as e:
        app.logger.exception("Vector search failed")
        return jsonify({"error": "Vector search failed", "detail": str(e)}), 500

    contexts = []
    for item in results:
        if isinstance(item, (list, tuple)):
            if len(item) == 3:
                doc_id, doc_text, score = item
            elif len(item) == 2:
                doc_id, doc_text = item
                score = None
            else:
                doc_id = getattr(item, "doc_id", None)
                doc_text = getattr(item, "text", str(item))
                score = None
        elif isinstance(item, dict):
            doc_id = item.get("doc_id")
            doc_text = item.get("document") or item.get("text") or ""
            score = item.get("score")
        else:
            doc_id = None
            doc_text = str(item)
            score = None
        contexts.append({"doc_id": doc_id, "text": doc_text, "score": score})

    # Build prompt:
    system_instructions = (
        "You are a legal assistant. You may use two inputs: "
        "(1) conversation history, which contains prior user/assistant turns in the same session, and "
        "(2) retrieved document context, which contains excerpts from indexed documents. "
        "Use conversation history only for conversational continuity, such as answering questions about what was asked earlier in the same session. "
        "Use retrieved document context for legal or document-grounded claims. "
        "Do not invent facts that are not supported by either source. "
        "Whenever you make a factual claim from retrieved documents, cite it using the exact format [source:doc.pdf chunk:2]. "
        "If the answer depends on prior conversation but no relevant session history is available, say that clearly. "
        "If the answer depends on document evidence but the retrieved context is insufficient, say what is known and what is unknown."
    )

    # messages begins with system instruction
    messages = [("system", system_instructions)]

    # include session history if available
    history_blocks = []
    if session_id:
        try:
            history = get_session_history(session_id, limit=CONTEXT_WINDOW)
            for m in history:
                r = m.get("role", "human")
                text = m.get("text", "")
                if text:
                    history_blocks.append(f"{r}: {text}")
                if r == "system":
                    messages.append(("system", text))
                elif r == "assistant":
                    messages.append(("assistant", text))
                else:
                    messages.append(("human", text))
        except Exception:
            app.logger.exception("Failed to fetch session history")

    # --- Graph expansion: extract entities from query and top contexts, query graph for related chunks (1-hop) ---
    entity_names = set()
    try:
        qdoc = nlp(query_text)
        for ent in qdoc.ents:
            if len(ent.text.strip()) > 2:
                entity_names.add(ent.text.strip())
    except Exception:
        app.logger.exception("spaCy failed on query")

    # also extract from top retrieved contexts (previews)
    for c in contexts:
        try:
            preview = (c.get("text") or "")[:1200]
            doc_sp = nlp(preview)
            for ent in doc_sp.ents:
                t = ent.text.strip()
                if len(t) > 2:
                    entity_names.add(t)
        except Exception:
            continue

    related_chunks = []
    if entity_names:
        try:
            related_chunks = graphstore.get_related_chunks_for_entities(list(entity_names), limit_per_entity=3)
        except Exception:
            app.logger.exception("Graph expansion failed (continuing without it)")
            related_chunks = []

    # Merge and dedupe contexts: vectors first, then graph neighbors
    merged_contexts = []
    seen_sigs = set()

    def _sig_from_preview(source, preview):
        return f"{source or 'graph'}::{hash((source, (preview or '')[:200]))}"

    # add vector contexts
    for i, c in enumerate(contexts):
        preview = (c.get("text") or "")[:1200]
        sig = _sig_from_preview(c.get("doc_id"), preview)
        if sig in seen_sigs:
            continue
        seen_sigs.add(sig)
        merged_contexts.append({
            "id": sig,
            "source": c.get("doc_id"),
            "text": c.get("text") or preview,
            "score": c.get("score"),
            "retrieval_type": "vector",
        })

    # add graph contexts
    for rc in related_chunks:
        cid = rc.get("id") or rc.get("chroma_id") or rc.get("preview")
        preview = rc.get("preview") or ""
        sig = _sig_from_preview(cid, preview)
        if sig in seen_sigs:
            continue
        seen_sigs.add(sig)
        merged_contexts.append({
            "id": cid,
            "source": rc.get("doc_id"),
            "text": preview,
            "score": None,
            "retrieval_type": "graph",
        })

    # build prompt context blocks (limit)
    prompt_blocks = []
    for i, c in enumerate(merged_contexts[:MAX_PROMPT_CHUNKS]):
        header = f"[source:{c.get('source') or 'graph'} chunk:{i}]"
        body = (c.get("text") or "")[:2000]
        prompt_blocks.append(f"{header}\n{body}")

    context_text = "\n\n---\n\n".join(prompt_blocks) if prompt_blocks else "No context retrieved."

    history_text = "\n".join(history_blocks[-CONTEXT_WINDOW:]) if history_blocks else "No prior conversation history available."

    human_prompt = (
        f"Conversation history:\n{history_text}\n\n"
        f"Retrieved document context:\n{context_text}\n\n"
        f"Current question: {query_text}\n\n"
        "Instructions:\n"
        "- If the user asks about something said earlier in this same session, answer from the conversation history.\n"
        "- If the user asks a legal or document-based question, answer from the retrieved document context and cite factual claims like [source:doc.pdf chunk:0].\n"
        "- If both are relevant, use both and clearly separate conversational memory from document-grounded claims.\n"
        "- If neither source is sufficient, say so clearly."
    )
    messages.append(("human", human_prompt))

    # Call LLM
    try:
        ai_response = llm.invoke(messages)
        answer = getattr(ai_response, "content", None)
        if isinstance(answer, list):
            answer = " ".join([a if isinstance(a, str) else str(a) for a in answer])
        answer = answer or str(ai_response)
    except Exception as e:
        app.logger.exception("LLM call failed")
        return jsonify({"error": "LLM call failed", "detail": str(e)}), 500

    # store assistant reply into session (if provided) and graph (message node + provenance links)
    if session_id:
        try:
            store_message(session_id, "assistant", answer)
        except Exception:
            app.logger.exception("Failed to store assistant response in Redis")

        try:
            reply_msg_id = str(uuid.uuid4())
            graphstore.store_message(session_id, reply_msg_id, "assistant", answer)
            # link message node to used chunk nodes (best-effort)
            for c in merged_contexts[:MAX_PROMPT_CHUNKS]:
                # attempt linking: if c['id'] matches a chunk id pattern in Neo4j this will work
                try:
                    graphstore.link_message_to_chunk(reply_msg_id, c.get("id"))
                except Exception:
                    # not all merged contexts will map to a graph chunk id - ignore failures
                    pass
        except Exception:
            app.logger.exception("Failed to store assistant message node in Neo4j")

    return jsonify({
        "query": query_text,
        "answer": answer,
        "sources": [
            {
                "source": c.get("source"),
                "retrieval_type": c.get("retrieval_type"),
                "excerpt": (c.get("text") or "")[:500],
                "chunk_id": c.get("id"),
                "score": c.get("score"),
            }
            for c in merged_contexts[:MAX_PROMPT_CHUNKS]
        ]
    }), 200


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify(message="OK", status="OK"), 200


if __name__ == '__main__':
    app.run(debug=True, port=int(os.getenv("PORT", "8000")), host="0.0.0.0")
