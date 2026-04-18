# src/rag/chunker.py

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)

RAW_DOCS_DIR = Path(os.getenv("RAG_RAW_DOCS_DIR", "knowledge_base/raw_docs"))
CHUNKS_PATH = Path(os.getenv("RAG_CHUNKS_PATH", "knowledge_base/chunks/knowledge_chunks.json"))

CHUNK_MAX_CHARS = int(os.getenv("RAG_CHUNK_MAX_CHARS", "1200"))
CHUNK_MIN_CHARS = int(os.getenv("RAG_CHUNK_MIN_CHARS", "80"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "120"))

HEADER_KEYS = {
    "title": re.compile(r"^TITLE\s*:\s*(.+)$", re.IGNORECASE),
    "source": re.compile(r"^SOURCE\s*:\s*(.+)$", re.IGNORECASE),
    "section": re.compile(r"^SECTION\s*:\s*(.+)$", re.IGNORECASE),
    "key_terms": re.compile(r"^KEY_TERMS\s*:\s*(.+)$", re.IGNORECASE),
    "actionable_guidance": re.compile(r"^ACTIONABLE_GUIDANCE\s*:\s*(.+)$", re.IGNORECASE),
}


# ──────────────────────────────────────────────────────────────────────────────
# Parsing
# ──────────────────────────────────────────────────────────────────────────────

def parse_document(text: str) -> tuple[dict[str, str | None], str]:
    """
    Extract structured header values from the top of a document and return
    the remaining body text separately.

    Returns (metadata_dict, body_text).
    """
    metadata: dict[str, str | None] = {key: None for key in HEADER_KEYS}
    lines = text.splitlines()
    body_lines: list[str] = []
    header_done = False

    for line in lines:
        stripped = line.strip()

        if header_done:
            body_lines.append(line)
            continue

        matched_any = False
        for key, pattern in HEADER_KEYS.items():
            match = pattern.match(stripped)
            if match:
                value = match.group(1).strip()
                if value:
                    metadata[key] = value
                matched_any = True
                break

        if not matched_any:
            header_done = True
            if stripped:
                body_lines.append(line)

    body = "\n".join(body_lines).strip()
    return metadata, body


# ──────────────────────────────────────────────────────────────────────────────
# Chunking
# ──────────────────────────────────────────────────────────────────────────────

def split_into_chunks(text: str) -> list[str]:
    """
    Split text into overlapping chunks of roughly CHUNK_MAX_CHARS characters.
    Splits are made at paragraph or sentence boundaries where possible.
    """
    paragraphs = re.split(r"\n{2,}", text.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_len = len(para)

        if current_len + para_len > CHUNK_MAX_CHARS and current:
            chunk_text = "\n\n".join(current).strip()
            if len(chunk_text) >= CHUNK_MIN_CHARS:
                chunks.append(chunk_text)

            overlap_text = _extract_overlap("\n\n".join(current))
            current = [overlap_text] if overlap_text else []
            current_len = len(overlap_text) if overlap_text else 0

        if para_len > CHUNK_MAX_CHARS:
            sub_chunks = _split_long_paragraph(para)
            for sub in sub_chunks:
                if current:
                    chunk_text = "\n\n".join(current).strip() + "\n\n" + sub
                    chunks.append(chunk_text.strip())
                    current = []
                    current_len = 0
                else:
                    chunks.append(sub)
        else:
            current.append(para)
            current_len += para_len + 2

    if current:
        chunk_text = "\n\n".join(current).strip()
        if len(chunk_text) >= CHUNK_MIN_CHARS:
            chunks.append(chunk_text)

    return chunks if chunks else [text.strip()]


def _extract_overlap(text: str) -> str:
    if not text or CHUNK_OVERLAP <= 0:
        return ""
    tail = text[-CHUNK_OVERLAP * 2:]
    sentences = re.split(r"(?<=[.!?])\s+", tail)
    if len(sentences) >= 2:
        return " ".join(sentences[-2:]).strip()
    return tail[-CHUNK_OVERLAP:].strip()


def _split_long_paragraph(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        s_len = len(sentence)
        if current_len + s_len > CHUNK_MAX_CHARS and current:
            chunks.append(" ".join(current).strip())
            current = [sentence]
            current_len = s_len
        else:
            current.append(sentence)
            current_len += s_len + 1

    if current:
        chunks.append(" ".join(current).strip())

    return [c for c in chunks if len(c) >= CHUNK_MIN_CHARS]


# ──────────────────────────────────────────────────────────────────────────────
# Chunk ID
# ──────────────────────────────────────────────────────────────────────────────

def make_chunk_id(doc_title: str | None, section: str | None, index: int, text: str) -> str:
    raw = f"{doc_title or ''}|{section or ''}|{index}|{text[:80]}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


# ──────────────────────────────────────────────────────────────────────────────
# Document processing
# ──────────────────────────────────────────────────────────────────────────────

def process_document(file_path: Path) -> list[dict]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception as exc:
        logger.error("Could not read %s: %s", file_path, exc)
        return []

    if not text:
        logger.warning("Empty file skipped: %s", file_path)
        return []

    metadata, body = parse_document(text)

    if not body:
        logger.warning("No body content found in %s after header parsing", file_path)
        return []

    title = metadata.get("title") or file_path.stem.replace("_", " ").replace("-", " ")
    source = metadata.get("source") or file_path.name
    section = metadata.get("section")

    key_terms_raw = metadata.get("key_terms") or ""
    key_terms: list[str] = [t.strip() for t in re.split(r"[,;]", key_terms_raw) if t.strip()]

    actionable = metadata.get("actionable_guidance")

    raw_chunks = split_into_chunks(body)

    if actionable:
        guidance_chunk = f"Actionable guidance:\n{actionable}"
        if guidance_chunk not in raw_chunks:
            raw_chunks.append(guidance_chunk)

    chunks: list[dict] = []
    for idx, chunk_text in enumerate(raw_chunks):
        chunk_text = chunk_text.strip()
        if len(chunk_text) < CHUNK_MIN_CHARS:
            continue

        chunk_id = make_chunk_id(title, section, idx, chunk_text)

        chunks.append(
            {
                "id": chunk_id,
                "title": title,
                "source": source,
                "section": section,
                "key_terms": key_terms,
                "chunk_text": chunk_text,
                "chunk_index": idx,
                "file": file_path.name,
            }
        )

    logger.info("Processed %s -> %d chunk(s)", file_path.name, len(chunks))
    return chunks


# ──────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────────────────────

def run_chunker(
    raw_docs_dir: Path = RAW_DOCS_DIR,
    chunks_path: Path = CHUNKS_PATH,
) -> list[dict]:
    raw_docs_dir = Path(raw_docs_dir)
    chunks_path = Path(chunks_path)

    if not raw_docs_dir.exists():
        logger.warning("Raw docs directory does not exist: %s", raw_docs_dir)
        raw_docs_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Created empty raw docs directory at %s", raw_docs_dir)

    txt_files = sorted(raw_docs_dir.glob("*.txt"))
    if not txt_files:
        logger.warning("No .txt files found in %s", raw_docs_dir)
        return []

    logger.info("Found %d document(s) in %s", len(txt_files), raw_docs_dir)

    all_chunks: list[dict] = []
    seen_ids: set[str] = set()

    for file_path in txt_files:
        doc_chunks = process_document(file_path)
        for chunk in doc_chunks:
            if chunk["id"] not in seen_ids:
                all_chunks.append(chunk)
                seen_ids.add(chunk["id"])

    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    with chunks_path.open("w", encoding="utf-8") as fh:
        json.dump(all_chunks, fh, ensure_ascii=False, indent=2)

    logger.info(
        "Wrote %d chunk(s) from %d document(s) to %s",
        len(all_chunks),
        len(txt_files),
        chunks_path,
    )

    return all_chunks


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Vispend AI knowledge base chunker")
    parser.add_argument(
        "--raw-docs",
        type=Path,
        default=RAW_DOCS_DIR,
        help="Directory containing .txt knowledge documents",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=CHUNKS_PATH,
        help="Output JSON path for generated chunks",
    )
    args = parser.parse_args()

    chunks = run_chunker(raw_docs_dir=args.raw_docs, chunks_path=args.out)
    print(f"Done. Wrote {len(chunks)} chunk(s) to {args.out}")