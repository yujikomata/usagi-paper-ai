"""
papers/ のテキストを分割して ChromaDB にインデックス化する。
埋め込みは Chroma 内蔵のローカルモデル（追加課金なし）を使用。

使い方:
    python build_index.py
"""
import glob
import json
import os

import chromadb

BASE = os.path.dirname(__file__)
PAPERS_DIR = os.path.join(BASE, "papers")
DB_DIR = os.path.join(BASE, "chroma_db")
COLLECTION = "usagi_papers"

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200


def read_meta():
    path = os.path.join(PAPERS_DIR, "index.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {m["file"]: m for m in data}


def parse_header(text):
    meta = {}
    body_start = 0
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "":
            body_start = i + 1
            break
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    body = "\n".join(lines[body_start:])
    return meta, body


def chunk_text(text):
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP
    return chunks


def main():
    meta_index = read_meta()
    client = chromadb.PersistentClient(path=DB_DIR)
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION)

    files = sorted(glob.glob(os.path.join(PAPERS_DIR, "*.txt")))
    docs, metas, ids = [], [], []
    total = 0

    for fpath in files:
        fname = os.path.basename(fpath)
        with open(fpath, encoding="utf-8") as f:
            raw = f.read()
        header, body = parse_header(raw)
        title = header.get("title", fname)
        for j, chunk in enumerate(chunk_text(body)):
            if len(chunk.strip()) < 50:
                continue
            docs.append(chunk)
            metas.append({
                "file": fname,
                "title": title,
                "year": header.get("year", ""),
                "journal": header.get("journal", ""),
                "doi": header.get("doi", ""),
                "source": header.get("source", ""),
            })
            ids.append(f"{fname}_{j}")
            total += 1

    # バッチ投入
    B = 200
    for i in range(0, len(docs), B):
        collection.add(
            documents=docs[i:i + B],
            metadatas=metas[i:i + B],
            ids=ids[i:i + B],
        )
        print(f"インデックス化 {min(i + B, len(docs))}/{len(docs)} チャンク")

    print(f"\n完了: {len(files)}本 / {total}チャンクを {DB_DIR} に保存")


if __name__ == "__main__":
    main()
