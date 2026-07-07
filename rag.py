"""Retrieval-Augmented Generation pipeline.

Document ingestion: loads .pdf/.txt files from `source_for_context`, splits
them into overlapping chunks, embeds them with Gemini embeddings and indexes
them in a FAISS vector store. Retrieval: similarity search against that index
so agents only receive the chunks relevant to the learner's goal instead of
whole documents.
"""
import os
from typing import List, Optional, Tuple

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

DEFAULT_CONTEXT_FOLDER = "source_for_context"
EMBEDDING_MODEL = "models/gemini-embedding-001"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def _resolve_folder(folder_name: str) -> Optional[str]:
    if os.path.isdir(folder_name):
        return folder_name
    fallback = os.path.join(os.path.dirname(os.path.abspath(__file__)), folder_name)
    if os.path.isdir(fallback):
        return fallback
    return None


def load_documents(folder_name: str = DEFAULT_CONTEXT_FOLDER) -> List[Document]:
    """Ingestion step 1: load every supported file in the context folder."""
    folder_path = _resolve_folder(folder_name)
    if folder_path is None:
        return []

    documents: List[Document] = []
    for file_name in sorted(os.listdir(folder_path)):
        file_path = os.path.join(folder_path, file_name)
        ext = os.path.splitext(file_name)[1].lower()
        try:
            if ext == '.txt':
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    documents.append(Document(page_content=f.read(), metadata={"source": file_name}))
            elif ext == '.pdf':
                for doc in PyMuPDF4LLMLoader(file_path).load():
                    if doc.page_content.strip():
                        doc.metadata["source"] = file_name
                        documents.append(doc)
        except Exception as e:
            # A single unreadable file should not sink the whole ingestion run.
            documents.append(Document(
                page_content=f"[Could not read {file_name}: {e}]",
                metadata={"source": file_name},
            ))
    return documents


def chunk_documents(documents: List[Document]) -> List[Document]:
    """Ingestion step 2: split documents into overlapping chunks sized for retrieval."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_documents(documents)


def build_vector_store(chunks: List[Document], api_key: Optional[str] = None) -> FAISS:
    """Ingestion step 3: embed chunks with Gemini and index them in FAISS."""
    embeddings = GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL,
        google_api_key=api_key or os.environ.get("GEMINI_API_KEY"),
    )
    return FAISS.from_documents(chunks, embeddings)


def ingest(folder_name: str = DEFAULT_CONTEXT_FOLDER, api_key: Optional[str] = None) -> Tuple[Optional[FAISS], List[str]]:
    """Full ingestion pipeline. Returns (vector_store, source_file_names).

    vector_store is None when the folder is empty or missing.
    """
    documents = load_documents(folder_name)
    if not documents:
        return None, []
    sources = sorted({d.metadata.get("source", "unknown") for d in documents})
    chunks = chunk_documents(documents)
    store = build_vector_store(chunks, api_key=api_key)
    return store, sources


def retrieve(store: FAISS, query: str, k: int = 6) -> str:
    """Similarity search: return the k most relevant chunks formatted for a prompt."""
    results = store.similarity_search(query, k=k)
    formatted = []
    for i, doc in enumerate(results, 1):
        source = doc.metadata.get("source", "unknown")
        formatted.append(f"[Chunk {i} | source: {source}]\n{doc.page_content}")
    return "\n\n".join(formatted)
