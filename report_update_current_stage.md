# Legal RAG Processor
## Updated Report Content Based on Current Project Stage

This draft updates the report so it reflects the system that is actually implemented in the current codebase. It is written to replace or revise the existing sections that currently mention unimplemented components such as blockchain verification, React frontend, and AWS deployment.

## 1. Updated Abstract

Accessing legal information in India remains difficult for many users because legal texts are lengthy, technical, and often scattered across multiple sources. To address this challenge, this project develops a Legal RAG (Retrieval-Augmented Generation) Processor that supports document ingestion, semantic retrieval, and grounded answer generation over legal documents. The system is built using a Flask backend, ChromaDB for vector retrieval, Neo4j for knowledge graph storage, Redis for session memory, spaCy for entity extraction, and Gemini through LangChain for response generation.

The current implementation allows users to upload legal documents in PDF, DOCX, and TXT formats, extract and chunk their contents, generate embeddings, and store them in a vector database for semantic search. In parallel, the system stores document, chunk, entity, and conversation relationships inside a graph database to support graph-aware retrieval and contextual expansion. A conversational query pipeline combines vector retrieval, graph-derived related chunks, and recent session history to produce concise answers grounded in the uploaded material.

At the present stage, the project successfully demonstrates a working backend for document indexing, session-aware querying, entity-aware graph enrichment, and grounded legal question answering. The system provides a strong foundation for future extensions such as richer graph reasoning, citation refinement, frontend integration, multilingual support, and secure document validation workflows.

## 2. Updated Introduction

The Indian legal ecosystem contains a vast and continuously growing body of statutes, policies, case materials, and regulatory documents. Although a large amount of legal information is available digitally, it is still difficult for users to search, interpret, and connect relevant information efficiently. Keyword-based approaches often fail because legal understanding depends heavily on context, semantics, and relationships between people, institutions, concepts, and provisions.

Retrieval-Augmented Generation (RAG) offers a practical solution by combining semantic retrieval with large language models. Instead of relying only on the model’s prior knowledge, a RAG system retrieves relevant passages from indexed legal documents and uses them to generate grounded answers. This improves relevance, reduces hallucination, and makes the responses more useful for legal information assistance.

The current version of the Legal RAG Processor focuses on building the core backend intelligence of such a system. It supports document upload, text extraction, chunking, embedding generation, semantic retrieval using ChromaDB, graph-based storage using Neo4j, conversation memory using Redis, and grounded response generation using Gemini via LangChain. In addition, entity extraction with spaCy is used to enrich graph nodes and support context expansion during query time.

Thus, the present project stage represents a functional backend-centered legal AI assistant capable of indexing legal text, retrieving relevant evidence, and producing concise answers backed by retrieved context. This implementation establishes the practical foundation on which more advanced deployment, verification, and personalization features can be added in the next phase.

## 3. Updated Objectives

The main objectives of the current project stage are:

1. To build a backend system capable of ingesting legal documents in PDF, DOCX, and TXT formats.
2. To extract, clean, and split documents into manageable text chunks for semantic processing.
3. To generate embeddings for document chunks and store them in ChromaDB for semantic retrieval.
4. To implement a query pipeline that retrieves relevant chunks based on user questions.
5. To generate grounded responses using a large language model with retrieved document context.
6. To maintain short-term conversational memory using Redis for session-aware interaction.
7. To construct a knowledge graph in Neo4j containing documents, chunks, entities, and conversation nodes.
8. To enrich uploaded document chunks using named entity recognition for graph-based legal context linking.
9. To combine vector retrieval and graph-based expansion to improve contextual answer generation.
10. To create a strong foundation for future work such as frontend integration, advanced graph reasoning, citation improvements, and document authenticity checks.

## 4. Updated Methodology

### 4.1 Document Ingestion

Users upload legal documents through the backend API. The current system accepts PDF, DOCX, and TXT files. Uploaded files are temporarily stored, processed for text extraction, and then removed from local temporary storage after processing.

### 4.2 Text Extraction and Chunking

Text is extracted using format-specific handling. PDF files are processed through PyPDF2, DOCX files through the `python-docx` library, and plain text files using standard file reading methods. The extracted document content is split into overlapping word-based chunks so that long documents can be indexed efficiently and retrieved with better locality of context.

### 4.3 Embedding Generation and Vector Storage

The chunked text is converted into dense embeddings using a Sentence Transformers model. These embeddings are stored in ChromaDB along with metadata such as document id and chunk index. This enables semantic similarity search instead of exact keyword matching.

### 4.4 Knowledge Graph Construction

For each indexed document, the system creates graph nodes representing the document and its chunks in Neo4j. It then applies named entity recognition using spaCy to identify important entities from chunk previews. These entities are added to the graph and linked to the chunk nodes through mention relationships. This allows the system to preserve lightweight structural knowledge in parallel with vector indexing.

### 4.5 Session Memory and Conversation Tracking

When a user initiates a session, the system generates a unique session id. Redis stores recent human and assistant messages for that session, enabling the query pipeline to include conversational context in future requests. The graph database also stores message nodes and their links to referenced chunk nodes where possible.

### 4.6 Query Processing

When a user asks a question, the system first retrieves semantically similar chunks from ChromaDB. It then extracts entities from the query and the top retrieved chunks, and uses these entities to request related chunk information from Neo4j. The retrieved vector contexts and graph-derived contexts are merged, deduplicated, and formatted into prompt blocks.

### 4.7 Answer Generation

The final prompt sent to the language model contains system instructions, optional recent session history, and the retrieved context blocks. Gemini, accessed through LangChain, generates a concise answer using only the available context. The prompt explicitly instructs the model to avoid unsupported claims and to cite context using source tokens.

## 5. Updated Tools and Techniques Used

### 5.1 Backend Framework

The backend is developed using Flask. Flask exposes REST endpoints for session creation, document upload, querying, and health checking. Its lightweight architecture makes it suitable for building and iterating on the RAG pipeline.

### 5.2 Language Model Integration

The project uses Gemini via the `langchain-google-genai` integration. LangChain is used to structure model invocation and support the conversational response pipeline.

### 5.3 Embedding and Vector Database

Semantic retrieval is implemented using Sentence Transformers for embedding generation and ChromaDB for vector storage and search. ChromaDB stores chunk embeddings and metadata required for document-level semantic retrieval.

### 5.4 Knowledge Graph

Neo4j is used as the graph database. It stores documents, chunks, entities, sessions, messages, and chunk references. This graph layer supports entity-based exploration and future personalization extensions.

### 5.5 Session Memory

Redis is used to maintain a rolling context window of recent messages per user session. This allows the system to preserve conversational continuity and improve multi-turn interactions.

### 5.6 Natural Language Processing

spaCy is used for named entity recognition. Extracted entities are linked to chunk nodes in Neo4j, helping the system connect relevant legal concepts and document fragments.

### 5.7 File Processing

PyPDF2 is used for PDF text extraction, `python-docx` for DOCX parsing, and standard text readers for TXT files. These components enable multi-format legal document ingestion.

## 6. Updated System Architecture Description

The current system architecture can be described as a backend-centric hybrid retrieval pipeline:

1. User uploads a legal document or submits a legal query.
2. Uploaded documents are processed through text extraction and chunking.
3. Chunks are embedded using Sentence Transformers.
4. Embeddings and metadata are stored in ChromaDB.
5. Document, chunk, and entity nodes are stored in Neo4j.
6. Session messages are stored in Redis and optionally also represented in Neo4j.
7. During query time, the system retrieves top semantic matches from ChromaDB.
8. Entities from the query and retrieved chunks are extracted using spaCy.
9. Related chunk information is requested from Neo4j.
10. Retrieved contexts are merged and passed to Gemini through LangChain.
11. The system returns a concise grounded answer with source-oriented citations.

## 7. Work Progress / Current Stage of Implementation

The current implementation status of the project is as follows:

### Completed Work

- Flask backend APIs for document upload, querying, session creation, and health checking are implemented.
- Multi-format document ingestion for PDF, DOCX, and TXT files is available.
- Text chunking and semantic embedding generation are implemented.
- ChromaDB-based indexing and retrieval are functional.
- Gemini-based answer generation through LangChain is integrated.
- Redis-based short-term session memory is implemented.
- Neo4j graph storage for documents, chunks, entities, sessions, and messages is implemented.
- spaCy-based entity extraction from uploaded content and query context is working.
- Hybrid retrieval behavior combining vector search and graph expansion is implemented.
- Response formatting has been improved to distinguish vector-derived and graph-derived sources.

### Partially Completed / In Progress

- Graph relationships for richer legal reasoning are still basic and currently centered around chunk-to-entity linking.
- Citation quality and source traceability have improved but still need further refinement.
- Error handling for encrypted PDFs, missing dependencies, and unreachable graph services is still being hardened.
- The system currently operates mainly as a backend API and does not yet include the previously proposed full React-based production frontend in this codebase.

### Planned Future Work

- Add a dedicated frontend interface for document upload and conversational querying.
- Strengthen graph reasoning with richer entity-to-entity and legal concept relationships.
- Improve prompt design, citation formatting, and source ranking.
- Support additional document types and robust OCR for scanned legal PDFs.
- Add multilingual capabilities for Indian legal use cases.
- Introduce verification, trust, or document provenance mechanisms in a later phase if required.
- Deploy the full system on cloud infrastructure after backend stabilization.

## 8. Updated Conclusion

The current stage of the Legal RAG Processor demonstrates a functional and meaningful implementation of a hybrid legal AI backend. The project has successfully integrated semantic retrieval, graph-based context enrichment, conversational session memory, and large language model response generation into a unified pipeline for legal document question answering.

Unlike a purely theoretical proposal, the present system already supports real document uploads, indexing, chunk-based embedding storage, entity extraction, graph modeling, and grounded response generation. This makes the project a practical prototype rather than only a conceptual design. At the same time, several advanced features originally envisioned for the broader system, such as blockchain-backed verification, production-grade frontend deployment, and more sophisticated personalization, should now be presented as future work rather than as completed components.

Therefore, the strongest and most accurate framing for the report at this stage is that the project has successfully built the core backend intelligence of a legal RAG platform and established a scalable base for future enhancement. This makes the work technically credible, academically solid, and well-positioned for the next phase of development.

## 9. Suggested Replacement Notes for Existing Report

Use these corrections while updating the original PDF or Word document:

- Replace references to "blockchain verification is implemented" with "document verification/provenance can be added in future work."
- Replace references to "React frontend is implemented" with "backend APIs are implemented; frontend integration is planned."
- Replace references to "AWS EC2 deployment is completed" with "deployment is planned after backend stabilization."
- Keep ChromaDB, Neo4j, Flask, and transformer-based retrieval as core implemented technologies.
- Emphasize that the present project stage is a working backend prototype with hybrid retrieval and session-aware legal QA.

## 10. Suggested Viva/Presentation Line

At the current stage, our project has successfully implemented the core backend pipeline of a Legal RAG system, including document ingestion, semantic retrieval with ChromaDB, graph-based context enrichment through Neo4j, session memory with Redis, and grounded answer generation using Gemini. Features such as blockchain-backed verification, full frontend integration, and production deployment are part of the planned next phase.
