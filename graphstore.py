# graphstore.py (NO APOC)
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

NEO4J_URL = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "password")

driver = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USER, NEO4J_PASS))

def _now_iso():
    return datetime.utcnow().isoformat() + "Z"

# ---- Constraints (no APOC needed) ----
def create_constraints_and_indexes():
    queries = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE"
    ]
    with driver.session() as s:
        for q in queries:
            s.run(q)

# ---- Document ----
def create_document(doc_id, title=None, source_url=None, doc_type=None):
    q = """
    MERGE (d:Document {id:$doc_id})
    SET d.title = $title,
        d.source_url = $source_url,
        d.type = $doc_type,
        d.created_at = COALESCE(d.created_at, $ts)
    """
    with driver.session() as s:
        s.run(q, doc_id=doc_id, title=title, source_url=source_url, doc_type=doc_type, ts=_now_iso())

# ---- Chunk ----
def create_chunk(doc_id, chunk_idx, text_preview, chroma_id=None):
    chunk_id = f"{doc_id}::chunk::{chunk_idx}"
    q = """
    MERGE (c:Chunk {id:$chunk_id})
    SET c.chunk_idx = $idx,
        c.text_preview = $preview,
        c.chroma_id = $chroma_id,
        c.created_at = COALESCE(c.created_at, $ts)
    WITH c
    MATCH (d:Document {id:$doc_id})
    MERGE (d)-[:HAS_CHUNK]->(c)
    """
    with driver.session() as s:
        s.run(q, chunk_id=chunk_id, idx=chunk_idx, preview=text_preview[:1200],
              chroma_id=chroma_id, doc_id=doc_id, ts=_now_iso())
    return chunk_id

# ---- Entity ----
def create_entity(name, ent_type=None):
    q = """
    MERGE (e:Entity {name:$name})
    SET e.type = COALESCE($ent_type, e.type)
    """
    with driver.session() as s:
        s.run(q, name=name, ent_type=ent_type)

def link_chunk_entity(chunk_id, entity_name):
    q = """
    MATCH (c:Chunk {id:$chunk_id})
    MERGE (e:Entity {name:$entity})
    MERGE (c)-[:MENTIONS]->(e)
    """
    with driver.session() as s:
        s.run(q, chunk_id=chunk_id, entity=entity_name)

# ---- Conversation message ----
def store_message(session_id, msg_id, role, text):
    q = """
    MERGE (s:Session {id:$session_id})
    MERGE (m:Message {id:$msg_id})
    SET m.role = $role, m.text = $text, m.ts = $ts
    MERGE (s)-[:HAS_MESSAGE]->(m)
    """
    with driver.session() as s:
        s.run(q, session_id=session_id, msg_id=msg_id,
              role=role, text=text, ts=_now_iso())

def link_message_to_chunk(msg_id, chunk_id):
    q = """
    MATCH (m:Message {id:$msg_id})
    MATCH (c:Chunk {id:$chunk_id})
    MERGE (m)-[:REFERENCED]->(c)
    """
    with driver.session() as s:
        s.run(q, msg_id=msg_id, chunk_id=chunk_id)

# ---- GRAPH EXPANSION WITHOUT APOC ----
def get_related_chunks_for_entities(entity_names, limit_per_entity=5):
    """
    NO APOC: simple match:
    - chunks directly mentioning the entity
    - chunks mentioning entities directly connected via RELATED_TO (1-hop)
    """
    q = """
    UNWIND $entities AS en
    MATCH (e:Entity {name:en})
    
    // chunks directly mentioning the entity
    OPTIONAL MATCH (e)<-[:MENTIONS]-(c1:Chunk)
    
    // chunks mentioning related entities (1 hop only)
    OPTIONAL MATCH (e)-[:RELATED_TO]-(e2:Entity)<-[:MENTIONS]-(c2:Chunk)
    
    WITH COLLECT(DISTINCT c1) + COLLECT(DISTINCT c2) AS chunks
    UNWIND chunks AS ch
    WITH DISTINCT ch
    OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(ch)
    WITH ch, d LIMIT $limit
    RETURN ch.id AS id, ch.text_preview AS preview, ch.chroma_id AS chroma_id, d.id AS doc_id
    """
    limit = limit_per_entity * len(entity_names)
    with driver.session() as s:
        data = s.run(q, entities=entity_names, limit=limit)
        return [r.data() for r in data]
