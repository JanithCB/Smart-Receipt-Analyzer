# src/rag/embedder.py

import json
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import numpy as np

logger = logging.getLogger(__name__)

CHUNKS_PATH   = Path(os.getenv("RAG_CHUNKS_PATH",    "knowledge_base/chunks/knowledge_chunks.json"))
INDEX_DIR     = Path(os.getenv("RAG_INDEX_DIR",      "knowledge_base/vector_index"))
INDEX_PATH    = INDEX_DIR / "faiss.index"
METADATA_PATH = INDEX_DIR / "metadata.json"
EMBED_MODEL   = os.getenv("RAG_EMBED_MODEL", "all-MiniLM-L6-v2")
BATCH_SIZE    = int(os.getenv("RAG_EMBED_BATCH_SIZE", "64"))


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def load_chunks(chunks_path: Path) -> list[dict]:
    if not chunks_path.exists():
        logger.error("Chunks file not found: %s", chunks_path)
        return []

    try:
        with chunks_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse chunks JSON at %s: %s", chunks_path, exc)
        return []

    if not isinstance(data, list):
        logger.error("Expected a JSON list in %s, got %s", chunks_path, type(data).__name__)
        return []

    logger.info("Loaded %d chunk(s) from %s", len(data), chunks_path)
    return data


def load_model(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers is required. Install it with:\n"
            "  pip install sentence-transformers"
        )

    logger.info("Loading embedding model: %s", model_name)
    model = SentenceTransformer(model_name)
    logger.info("Model loaded")
    return model


def embed_texts(model, texts: list[str]) -> np.ndarray:
    logger.info("Embedding %d text(s) in batches of %d", len(texts), BATCH_SIZE)

    all_embeddings: list[np.ndarray] = []

    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        embeddings = model.encode(
            batch,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        all_embeddings.append(embeddings)
        logger.debug("Embedded batch %d–%d", start, start + len(batch) - 1)

    result = np.vstack(all_embeddings).astype(np.float32)
    logger.info("Embedding complete. Shape: %s", result.shape)
    return result


def build_faiss_index(embeddings: np.ndarray):
    try:
        import faiss
    except ImportError:
        raise ImportError(
            "faiss-cpu is required. Install it with:\n"
            "  pip install faiss-cpu"
        )

    dimension = embeddings.shape[1]
    logger.info("Building FAISS IndexFlatIP with dimension %d", dimension)

    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    logger.info("FAISS index built with %d vector(s)", index.ntotal)
    return index


def save_index(index, index_path: Path) -> None:
    try:
        import faiss
    except ImportError:
        raise ImportError("faiss-cpu is required to save the index.")

    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))
    logger.info("FAISS index saved to %s", index_path)


def save_metadata(chunks: list[dict], metadata_path: Path) -> None:
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    meta_records = []
    for chunk in chunks:
        meta_records.append(
            {
                "id":          chunk.get("id"),
                "title":       chunk.get("title"),
                "source":      chunk.get("source"),
                "section":     chunk.get("section"),
                "key_terms":   chunk.get("key_terms", []),
                "chunk_text":  chunk.get("chunk_text", ""),
                "chunk_index": chunk.get("chunk_index", 0),
                "file":        chunk.get("file"),
            }
        )

    with metadata_path.open("w", encoding="utf-8") as fh:
        json.dump(meta_records, fh, ensure_ascii=False, indent=2)

    logger.info("Metadata saved to %s  (%d record(s))", metadata_path, len(meta_records))


# ──────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────────────────────


def run_embedder(
    chunks_path:   Path = CHUNKS_PATH,
    index_path:    Path = INDEX_PATH,
    metadata_path: Path = METADATA_PATH,
    model_name:    str  = EMBED_MODEL,
) -> None:
    chunks_path   = Path(chunks_path)
    index_path    = Path(index_path)
    metadata_path = Path(metadata_path)

    chunks = load_chunks(chunks_path)
    if not chunks:
        logger.error("No chunks to embed. Run chunker.py first.")
        return

    texts = [chunk.get("chunk_text", "") for chunk in chunks]
    empty = [i for i, t in enumerate(texts) if not t.strip()]
    if empty:
        logger.warning("Skipping %d chunk(s) with empty text", len(empty))
        chunks = [c for i, c in enumerate(chunks) if i not in set(empty)]
        texts  = [t for i, t in enumerate(texts)  if i not in set(empty)]

    if not texts:
        logger.error("All chunks had empty text. Nothing to embed.")
        return

    model      = load_model(model_name)
    embeddings = embed_texts(model, texts)
    index      = build_faiss_index(embeddings)

    save_index(index, index_path)
    save_metadata(chunks, metadata_path)

    logger.info(
        "Embedder complete. %d vector(s) stored. Index: %s  Metadata: %s",
        index.ntotal,
        index_path,
        metadata_path,
    )


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Vispend AI knowledge base embedder")
    parser.add_argument(
        "--chunks",
        type=Path,
        default=CHUNKS_PATH,
        help="Path to the chunks JSON file produced by chunker.py",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=INDEX_DIR,
        help="Directory to save the FAISS index and metadata",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=EMBED_MODEL,
        help="SentenceTransformer model name",
    )
    args = parser.parse_args()

    resolved_index    = Path(args.index_dir) / "faiss.index"
    resolved_metadata = Path(args.index_dir) / "metadata.json"

    run_embedder(
        chunks_path=args.chunks,
        index_path=resolved_index,
        metadata_path=resolved_metadata,
        model_name=args.model,
    )

    print(f"Done. Index saved to {resolved_index}")