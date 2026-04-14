import os
import json
import uuid

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_DIR = os.path.join(BASE_DIR, "knowledge_base", "raw_docs")
CHUNKS_DIR = os.path.join(BASE_DIR, "knowledge_base", "chunks")
OUTPUT_PATH = os.path.join(CHUNKS_DIR, "knowledge_chunks.json")

os.makedirs(CHUNKS_DIR, exist_ok=True)


def parse_header(lines):
    meta = {
        "doc_title": "",
        "source": "",
        "document_type": "",
        "topics": [],
        "summary": "",
    }

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("TITLE:"):
            meta["doc_title"] = line[len("TITLE:"):].strip()
        elif line.startswith("SOURCE:"):
            meta["source"] = line[len("SOURCE:"):].strip()
        elif line.startswith("DOCUMENT_TYPE:"):
            meta["document_type"] = line[len("DOCUMENT_TYPE:"):].strip()
        elif line.startswith("TOPICS:"):
            meta["topics"] = [t.strip() for t in line[len("TOPICS:"):].split(",") if t.strip()]
        elif line.startswith("SUMMARY:"):
            summary_lines = [line[len("SUMMARY:"):].strip()]
            i += 1
            while i < len(lines):
                next_line = lines[i].strip()
                if next_line.startswith(("SECTION:", "KEY_TERMS:", "ACTIONABLE_GUIDANCE:")):
                    break
                if next_line:
                    summary_lines.append(next_line)
                i += 1
            meta["summary"] = " ".join(summary_lines)
            continue
        elif line.startswith("SECTION:"):
            break

        i += 1

    return meta, i


def split_blocks(lines, start_idx):
    blocks = []
    current_type = None
    current_title = ""
    current_lines = []

    def flush():
        if current_type and current_lines:
            blocks.append((current_type, current_title, list(current_lines)))

    for i in range(start_idx, len(lines)):
        line = lines[i].strip()

        if line.startswith("SECTION:"):
            flush()
            current_type = "section"
            current_title = line[len("SECTION:"):].strip()
            current_lines = []

        elif line.startswith("KEY_TERMS:"):
            flush()
            current_type = "key_terms"
            current_title = "Key Terms"
            current_lines = []

        elif line.startswith("ACTIONABLE_GUIDANCE:"):
            flush()
            current_type = "actionable_guidance"
            current_title = "Actionable Guidance"
            current_lines = []

        else:
            if current_type and line:
                current_lines.append(line)

    flush()
    return blocks


def build_chunks(meta, blocks, file_name):
    chunks = []

    base = {
        "doc_title": meta["doc_title"],
        "source": meta["source"],
        "document_type": meta["document_type"],
        "topics": meta["topics"],
        "file_name": file_name,
    }

    if meta["summary"]:
        chunks.append({
            **base,
            "chunk_id": str(uuid.uuid4()),
            "section_title": "Document Summary",
            "chunk_type": "summary",
            "text": meta["summary"],
        })

    for block_type, block_title, block_lines in blocks:
        text = "\n".join(block_lines).strip()
        if not text:
            continue

        chunks.append({
            **base,
            "chunk_id": str(uuid.uuid4()),
            "section_title": block_title,
            "chunk_type": block_type,
            "text": text,
        })

    return chunks


def chunk_document(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    meta, start_idx = parse_header(lines)
    blocks = split_blocks(lines, start_idx)
    return build_chunks(meta, blocks, os.path.basename(file_path))


def main():
    print("BASE_DIR   =", BASE_DIR)
    print("RAW_DIR    =", RAW_DIR)
    print("CHUNKS_DIR =", CHUNKS_DIR)

    if not os.path.exists(RAW_DIR):
        print(f"[ERROR] Folder not found: {RAW_DIR}")
        return

    txt_files = [f for f in os.listdir(RAW_DIR) if f.endswith(".txt")]
    if not txt_files:
        print(f"[ERROR] No .txt files found in {RAW_DIR}")
        return

    all_chunks = []

    for file_name in txt_files:
        file_path = os.path.join(RAW_DIR, file_name)
        chunks = chunk_document(file_path)
        all_chunks.extend(chunks)
        print(f"{file_name} -> {len(chunks)} chunks")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)

    print(f"\nTotal chunks: {len(all_chunks)}")
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()