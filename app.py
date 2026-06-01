"""
うさぎ論文AI — Streamlit チャットアプリ
論文（ChromaDB）から関連箇所を検索し、Claudeが引用つきで回答する。
"""
import os

# protobuf の C実装とランタイムの不整合を回避（chromadb import前に設定）
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

import chromadb
import streamlit as st
from anthropic import Anthropic

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)  # .env の値を環境変数より優先
except Exception:
    pass

import glob

BASE = os.path.dirname(__file__)
PAPERS_DIR = os.path.join(BASE, "papers")
COLLECTION = "usagi_papers"
MODEL = "claude-sonnet-4-6"
TOP_K = 10
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200

# Streamlit Cloud の Secrets か環境変数からキーを取得
API_KEY = os.getenv("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", "")

st.set_page_config(page_title="うさぎ論文AI / Rabbit Paper AI", page_icon="🐰")
st.title("🐰 うさぎ論文AI")
st.caption("世界中のオープンアクセスのうさぎ論文に基づいて回答します / Answers grounded in open-access rabbit research papers")


@st.cache_data
def load_paper_list():
    import json
    path = os.path.join(PAPERS_DIR, "index.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return sorted(data, key=lambda x: (str(x.get("year", "")), x.get("title", "")), reverse=True)


with st.sidebar:
    papers = load_paper_list()
    st.header(f"📚 収録論文一覧（{len(papers)}本）")
    st.caption("出典: Europe PMC オープンアクセス論文")
    kw = st.text_input("タイトルで絞り込み", "")
    shown = [p for p in papers if kw.lower() in p.get("title", "").lower()] if kw else papers
    st.caption(f"{len(shown)}本を表示")
    for p in shown[:300]:
        doi = p.get("doi", "")
        title = p.get("title", "")
        year = p.get("year", "")
        if doi:
            st.markdown(f"- [{title}](https://doi.org/{doi}) ({year})")
        else:
            st.markdown(f"- {title} ({year})")
    if len(shown) > 300:
        st.caption(f"…ほか {len(shown) - 300} 本（絞り込み検索をご利用ください）")


def _parse_header(text):
    meta, body_start = {}, 0
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "":
            body_start = i + 1
            break
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    return meta, "\n".join(lines[body_start:])


def _chunk(text):
    out, start = [], 0
    while start < len(text):
        out.append(text[start:start + CHUNK_SIZE])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return out


@st.cache_resource(show_spinner="論文データベースを構築中...（初回のみ少し時間がかかります）")
def get_collection():
    # HNSWバイナリはOS/CPU依存で移植できないため、起動時にテキストから構築する
    client = chromadb.EphemeralClient()
    col = client.create_collection(COLLECTION)
    docs, metas, ids = [], [], []
    for fpath in sorted(glob.glob(os.path.join(PAPERS_DIR, "*.txt"))):
        fname = os.path.basename(fpath)
        with open(fpath, encoding="utf-8") as f:
            header, body = _parse_header(f.read())
        title = header.get("title", fname)
        for j, ch in enumerate(_chunk(body)):
            if len(ch.strip()) < 50:
                continue
            # タイトルをチャンク先頭に付与し、論文タイトルの語も検索対象にする
            docs.append(f"{title}\n{ch}")
            metas.append({"title": title, "year": header.get("year", "")})
            ids.append(f"{fname}_{j}")
    for i in range(0, len(docs), 200):
        col.add(documents=docs[i:i + 200], metadatas=metas[i:i + 200], ids=ids[i:i + 200])
    return col


@st.cache_resource
def get_client():
    return Anthropic(api_key=API_KEY)


SYSTEM = (
    "あなたはうさぎ研究論文の専門アシスタントです。"
    "渡された論文の抜粋（コンテキスト）だけに基づいて回答してください。"
    "コンテキストに情報がない場合は推測せず、その旨を正直に伝えてください。"
    "回答の言語は質問された言語に合わせてください（日本語の質問には日本語、英語の質問には英語）。"
    "回答の最後に、使用した論文を [タイトル (年)] の形式で列挙してください。"
)


def to_search_query(question: str) -> str:
    """論文は英語なので、検索用に質問を英語キーワードへ変換する。"""
    try:
        msg = get_client().messages.create(
            model=MODEL,
            max_tokens=80,
            system="Translate the user's question into concise English search keywords for a scientific paper database about rabbits. Output only the keywords, no explanation.",
            messages=[{"role": "user", "content": question}],
        )
        return msg.content[0].text.strip()
    except Exception:
        return question


def build_context(question: str):
    col = get_collection()
    search_q = to_search_query(question)
    res = col.query(query_texts=[search_q], n_results=TOP_K)
    docs = res["documents"][0]
    metas = res["metadatas"][0]
    blocks, sources = [], []
    for d, m in zip(docs, metas):
        tag = f"{m.get('title','?')} ({m.get('year','')})"
        blocks.append(f"[出典: {tag}]\n{d}")
        if tag not in sources:
            sources.append(tag)
    return "\n\n---\n\n".join(blocks), sources


if not API_KEY:
    st.error("APIキーが設定されていません。Streamlit Cloud の Secrets に ANTHROPIC_API_KEY を設定してください。")
    st.stop()

if not glob.glob(os.path.join(PAPERS_DIR, "*.txt")):
    st.error("論文データが見つかりません。先に ingest.py を実行してください。")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("うさぎについて質問してください / Ask about rabbits"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("論文を検索中..."):
            context, sources = build_context(prompt)
        user_msg = (
            f"以下の論文抜粋（コンテキスト）に基づいて質問に答えてください。\n\n"
            f"=== コンテキスト ===\n{context}\n\n=== 質問 ===\n{prompt}"
        )
        stream_box = st.empty()
        answer = ""
        with get_client().messages.stream(
            model=MODEL,
            max_tokens=1500,
            system=SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            for text in stream.text_stream:
                answer += text
                stream_box.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
