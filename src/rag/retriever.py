# src/rag/retriever.py
"""
retriever.py — Vispend AI RAG Pipeline
Semantic search over chunk embeddings.
"""

import os
import json
import logging
import numpy as np

logger = logging.getLogger(__name__)

BASE_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VECTOR_DIR = os.path.join(BASE_DIR, "knowledge_base", "vector_index")
INDEX_PATH = os.path.join(VECTOR_DIR, "faiss.index")
META_PATH  = os.path.join(VECTOR_DIR, "metadata.json")
MODEL_NAME = "all-MiniLM-L6-v2"


class Retriever:
    def __init__(self):
        self.index    = None
        self.metadata = None
        self.model    = None

    def _load(self):
        if self.index is not None:
            return

        import faiss
        from sentence_transformers import SentenceTransformer

        # Fix: print() → logger.debug() — no debug output in production
        logger.debug("BASE_DIR   = %s", BASE_DIR)
        logger.debug("VECTOR_DIR = %s", VECTOR_DIR)
        logger.debug("INDEX_PATH = %s", INDEX_PATH)
        logger.debug("META_PATH  = %s", META_PATH)

        if not os.path.exists(INDEX_PATH):
            raise FileNotFoundError(
                f"FAISS index not found: {INDEX_PATH}\nRun embedder.py first."
            )
        if not os.path.exists(META_PATH):
            raise FileNotFoundError(
                f"Metadata file not found: {META_PATH}"
            )

        self.index = faiss.read_index(INDEX_PATH)

        with open(META_PATH, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        self.model = SentenceTransformer(MODEL_NAME)
        logger.info("Retriever loaded — %d chunks indexed.", len(self.metadata))

    def retrieve(self, query: str, top_k: int = 5) -> list:
        self._load()

        query_vec = self.model.encode(
            [query], convert_to_numpy=True
        ).astype("float32")

        norm      = np.linalg.norm(query_vec, axis=1, keepdims=True)
        query_vec = query_vec / np.where(norm == 0, 1, norm)

        scores, indices = self.index.search(query_vec, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            chunk          = dict(self.metadata[idx])
            chunk["score"] = round(float(score), 4)
            results.append(chunk)

        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    retriever = Retriever()

    test_queries = [
        "how do I reduce food spending?",
        "what is the 50-30-20 rule?",
        "what should I do if expenses are greater than income?",
        "how do I track small daily purchases?",
        "what are the benefits of using a bank?",
    ]

    for query in test_queries:
        print(f"\nQuery: {query}")
        results = retriever.retrieve(query, top_k=3)
        for r in results:
            print(f"  [{r['score']}] {r['doc_title']} → {r['section_title']}")