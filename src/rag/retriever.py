# src/rag/retriever.py

import json
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

INDEX_DIR     = Path(os.getenv("RAG_INDEX_DIR",   "knowledge_base/vector_index"))
INDEX_PATH    = INDEX_DIR / "faiss.index"
METADATA_PATH = INDEX_DIR / "metadata.json"
EMBED_MODEL   = os.getenv("RAG_EMBED_MODEL", "all-MiniLM-L6-v2")
DEFAULT_TOP_K = int(os.getenv("RAG_DEFAULT_TOP_K", "5"))


class Retriever:
    def __init__(
        self,
        index_path:    Path | str = INDEX_PATH,
        metadata_path: Path | str = METADATA_PATH,
        model_name:    str        = EMBED_MODEL,
    ) -> None:
        self._index_path    = Path(index_path)
        self._metadata_path = Path(metadata_path)
        self._model_name    = model_name

        self._model    = None
        self._index    = None
        self._metadata: list[dict] = []
        self._ready    = False

    # ──────────────────────────────────────────────────────────
    # Lazy initialisation
    # ──────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> bool:
        if self._ready:
            return True

        if not self._index_path.exists():
            logger.error(
                "FAISS index not found at %s. Run embedder.py first.",
                self._index_path,
            )
            return False

        if not self._metadata_path.exists():
            logger.error(
                "Metadata file not found at %s. Run embedder.py first.",
                self._metadata_path,
            )
            return False

        if not self._load_index():
            return False

        if not self._load_metadata():
            return False

        if not self._load_model():
            return False

        self._ready = True
        return True

    def _load_index(self) -> bool:
        try:
            import faiss
        except ImportError:
            logger.error(
                "faiss-cpu is not installed. Install it with: pip install faiss-cpu"
            )
            return False

        try:
            self._index = faiss.read_index(str(self._index_path))
            logger.info(
                "FAISS index loaded from %s  (%d vector(s))",
                self._index_path,
                self._index.ntotal,
            )
            return True
        except Exception as exc:
            logger.error("Failed to load FAISS index from %s: %s", self._index_path, exc)
            return False

    def _load_metadata(self) -> bool:
        try:
            with self._metadata_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)

            if not isinstance(data, list):
                logger.error(
                    "Expected a JSON list in metadata file, got %s",
                    type(data).__name__,
                )
                return False

            self._metadata = data
            logger.info(
                "Metadata loaded from %s  (%d record(s))",
                self._metadata_path,
                len(self._metadata),
            )
            return True
        except json.JSONDecodeError as exc:
            logger.error(
                "Failed to parse metadata JSON at %s: %s",
                self._metadata_path,
                exc,
            )
            return False
        except Exception as exc:
            logger.error(
                "Unexpected error loading metadata from %s: %s",
                self._metadata_path,
                exc,
            )
            return False

    def _load_model(self) -> bool:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.error(
                "sentence-transformers is not installed. "
                "Install it with: pip install sentence-transformers"
            )
            return False

        try:
            self._model = SentenceTransformer(self._model_name)
            logger.info("Embedding model loaded: %s", self._model_name)
            return True
        except Exception as exc:
            logger.error(
                "Failed to load embedding model %s: %s",
                self._model_name,
                exc,
            )
            return False

    # ──────────────────────────────────────────────────────────
    # Embedding
    # ──────────────────────────────────────────────────────────

    def _embed_query(self, query: str) -> np.ndarray | None:
        if self._model is None:
            return None

        try:
            embedding = self._model.encode(
                [query],
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            return embedding.astype(np.float32)
        except Exception as exc:
            logger.error("Failed to embed query: %s", exc)
            return None

    # ──────────────────────────────────────────────────────────
    # Search
    # ──────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
        """
        Embed the query and return the top_k most similar knowledge chunks.

        Each result dict contains:
            chunk_text, score, source, title, section, key_terms
        """
        if not query or not query.strip():
            logger.warning("Empty query passed to Retriever.search — returning []")
            return []

        if not self._ensure_loaded():
            logger.warning("Retriever not ready — returning empty results")
            return []

        if self._index is None or not self._metadata:
            return []

        query_vector = self._embed_query(query.strip())
        if query_vector is None:
            return []

        effective_k = min(top_k, self._index.ntotal)
        if effective_k <= 0:
            return []

        try:
            scores, indices = self._index.search(query_vector, effective_k)
        except Exception as exc:
            logger.error("FAISS search failed: %s", exc)
            return []

        results: list[dict[str, Any]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._metadata):
                continue

            record = self._metadata[idx]
            results.append(
                {
                    "chunk_text": record.get("chunk_text", ""),
                    "score":      float(score),
                    "source":     record.get("source"),
                    "title":      record.get("title"),
                    "section":    record.get("section"),
                    "key_terms":  record.get("key_terms", []),
                    "chunk_index": record.get("chunk_index", 0),
                    "id":         record.get("id"),
                }
            )

        logger.debug(
            "Search for %r returned %d result(s)  (top score: %.4f)",
            query[:60],
            len(results),
            results[0]["score"] if results else 0.0,
        )

        return results

    # ──────────────────────────────────────────────────────────
    # Status
    # ──────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def vector_count(self) -> int:
        if self._index is not None:
            return self._index.ntotal
        return 0

    def __repr__(self) -> str:
        return (
            f"Retriever(model={self._model_name!r}, "
            f"vectors={self.vector_count}, ready={self._ready})"
        )


# ──────────────────────────────────────────────────────────────────────────────
# CLI smoke test
# ──────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Vispend AI retriever smoke test")
    parser.add_argument(
        "--query",
        type=str,
        default="How can I reduce my grocery spending?",
        help="Query to test retrieval",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Number of results to return",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=INDEX_DIR,
        help="Directory containing faiss.index and metadata.json",
    )
    args = parser.parse_args()

    retriever = Retriever(
        index_path=Path(args.index_dir) / "faiss.index",
        metadata_path=Path(args.index_dir) / "metadata.json",
    )

    results = retriever.search(args.query, top_k=args.top_k)

    if not results:
        print("No results returned. Check that embedder.py has been run.")
    else:
        print(f"\nQuery: {args.query}\n")
        for i, r in enumerate(results, start=1):
            print(f"[{i}]  score={r['score']:.4f}  title={r['title']}  source={r['source']}")
            print(f"     {r['chunk_text'][:200].strip()}")
            print()