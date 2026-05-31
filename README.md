# 🐰 うさぎ論文AI / Rabbit Paper AI

世界中のオープンアクセスのうさぎ論文を集め、その内容に基づいて質問に答えるAI（NotebookLM風）。
Claude API + ChromaDB + Streamlit で構築。日本語・英語の両方に対応。

---

## セットアップ手順

### 1. パッケージのインストール
```bash
cd usagi-paper-ai
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. APIキーの設定（ローカル）
`.env.example` を `.env` にコピーして、新しいAPIキーを貼り付ける:
```
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. 論文を収集（120本以上）
```bash
python ingest.py --count 150
```
Europe PMC（無料・APIキー不要）からオープンアクセスのうさぎ論文を集めます。

### 4. インデックス化
```bash
python build_index.py
```

### 5. ローカルで起動
```bash
streamlit run app.py
```
→ ブラウザで http://localhost:8501 が開きます。

---

## URLで公開する（Streamlit Cloud・無料）

1. このフォルダをGitHubリポジトリにプッシュ
   （`.env` と `chroma_db/` は `.gitignore` で除外済み）
2. https://share.streamlit.io にGitHubアカウントでログイン
3. 「New app」→ リポジトリと `app.py` を選択
4. 「Advanced settings」→「Secrets」に以下を貼り付け:
   ```
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
5. Deploy → 公開URLが発行されます

> ⚠️ 注意: `chroma_db/` は `.gitignore` で除外されています。
> クラウドで論文DBを使うには、`build_index.py` で作った `chroma_db/`
> をリポジトリに含める（gitignoreから外す）か、起動時に再構築する必要があります。
> 手軽さ重視なら、`.gitignore` の `chroma_db/` 行を削除してDBごとコミットするのが簡単です。

---

## コストの目安
- 論文収集・インデックス化: 無料（Europe PMC + ローカル埋め込み）
- 質問への回答: Claude API の従量課金（1質問あたり数円程度）

## 著作権について
収集対象は Europe PMC の **オープンアクセス論文のみ**。利用時は各論文のライセンスをご確認ください。
