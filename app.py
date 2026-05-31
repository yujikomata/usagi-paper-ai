"""
うさぎ論文AI — Streamlit チャットアプリ
論文（ChromaDB）から関連箇所を検索し、Claudeが引用つきで回答する。
"""
import os

import chromadb
import streamlit as st
from anthropic import Anthropic

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)  # .env の値を環境変数より優先
except Exception:
    pass

BASE = os.path.dirname(__file__)
DB_DIR = os.path.join(BASE, "chroma_db")
COLLECTION = "usagi_papers"
MODEL = "claude-sonnet-4-6"
TOP_K = 6

# Streamlit Cloud の Secrets か環境変数からキーを取得
API_KEY = os.getenv("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", "")

st.set_page_config(page_title="うさぎ論文AI / Rabbit Paper AI", page_icon="🐰")
st.title("🐰 うさぎ論文AI")
st.caption("世界中のオープンアクセスのうさぎ論文に基づいて回答します / Answers grounded in open-access rabbit research papers")


@st.cache_resource
def get_collection():
    client = chromadb.PersistentClient(path=DB_DIR)
    return client.get_collection(COLLECTION)


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

if not os.path.exists(DB_DIR):
    st.error("論文インデックスが見つかりません。先に ingest.py と build_index.py を実行してください。")
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
