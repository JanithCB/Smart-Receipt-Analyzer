"""
embedder.py — Vispend AI RAG Pipeline

Reads:
    knowledge_base/chunks/knowledge_chunks.json

Writes:
    knowledge_base/vector_index/faiss.index
    knowledge_base/vector_index/metadata.json
"""

import os
import json
import numpy as np

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHUNKS_PATH = os.path.join(BASE_DIR, "knowledge_base", "chunks", "knowledge_chunks.json")
VECTOR_DIR = os.path.join(BASE_DIR, "knowledge_base", "vector_index")
INDEX_PATH = os.path.join(VECTOR_DIR, "faiss.index")
META_PATH = os.path.join(VECTOR_DIR, "metadata.json")
MODEL_NAME = "all-MiniLM-L6-v2"

os.makedirs(VECTOR_DIR, exist_ok=True)


def main():
    from sentence_transformers import SentenceTransformer
    import faiss

    print("BASE_DIR   =", BASE_DIR)
    print("CHUNKS_PATH =", CHUNKS_PATH)
    print("VECTOR_DIR =", VECTOR_DIR)

    if not os.path.exists(CHUNKS_PATH):
        print(f"[ERROR] Chunks file not found: {CHUNKS_PATH}")
        print("Run chunker.py first.")
        return

    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    texts = [chunk["text"] for chunk in chunks]

    print(f"Loaded {len(chunks)} chunks")
    print("Generating embeddings...")

    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode(
        texts,
        show_progress_bar=True,
        convert_to_numpy=True
    ).astype("float32")

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / np.where(norms == 0, 1, norms)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    faiss.write_index(index, INDEX_PATH)

    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    print(f"FAISS index saved to: {INDEX_PATH}")
    print(f"Metadata saved to: {META_PATH}")
    print(f"Vectors stored: {index.ntotal}")
    print(f"Embedding dimension: {dim}")


if __name__ == "__main__":
    main()