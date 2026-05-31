"""
うさぎ論文を Europe PMC（無料・APIキー不要）から収集し、
本文テキストを papers/ に保存するスクリプト。

使い方:
    python ingest.py            # デフォルト150本収集
    python ingest.py --count 200
"""
import argparse
import html
import json
import os
import re
import time

import requests


def clean(text: str) -> str:
    """HTMLエンティティとインラインタグを除去する。"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()

PAPERS_DIR = os.path.join(os.path.dirname(__file__), "papers")
SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{source}/{pid}/fullTextXML"

# うさぎが主役の論文に絞るため、タイトルにうさぎ関連語を含むものを検索
QUERY = (
    '(TITLE:rabbit OR TITLE:rabbits OR TITLE:"Oryctolagus" OR TITLE:leporid '
    'OR TITLE:lagomorph OR TITLE:cuniculi OR TITLE:cuniculus OR TITLE:myxomatosis '
    'OR TITLE:bunny OR TITLE:"rabbit hemorrhagic") '
    'AND (OPEN_ACCESS:y) AND (LANG:eng)'
)


def sanitize(name: str) -> str:
    name = re.sub(r"[^\w\-]+", "_", name)
    return name[:80].strip("_")


def strip_xml(xml: str) -> str:
    """XML本文からタグを除去してプレーンテキスト化する簡易処理。"""
    text = re.sub(r"<ref-list.*?</ref-list>", "", xml, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_fulltext(source: str, pid: str) -> str:
    url = FULLTEXT_URL.format(source=source, pid=pid)
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and r.text.strip():
            return strip_xml(r.text)
    except requests.RequestException:
        pass
    return ""


def search(count: int):
    os.makedirs(PAPERS_DIR, exist_ok=True)
    saved = 0
    cursor = "*"
    page_size = 100
    meta_index = []

    while saved < count:
        params = {
            "query": QUERY,
            "format": "json",
            "pageSize": page_size,
            "cursorMark": cursor,
            "resultType": "core",
        }
        r = requests.get(SEARCH_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        results = data.get("resultList", {}).get("result", [])
        if not results:
            break

        for item in results:
            if saved >= count:
                break
            pmid = item.get("id")
            source = item.get("source", "MED")
            title = clean(item.get("title", "untitled"))
            abstract = clean(item.get("abstractText", ""))
            year = item.get("pubYear", "")
            journal = item.get("journalTitle", "")
            doi = item.get("doi", "")

            body = ""
            if item.get("hasTextMinedTerms") or item.get("inEPMC") == "Y":
                body = fetch_fulltext(source, pmid)
                time.sleep(0.3)

            content = body if len(body) > len(abstract or "") else (abstract or "")
            if not content or len(content) < 200:
                continue

            slug = sanitize(f"{year}_{pmid}_{title}")
            fname = f"{slug}.txt"
            header = (
                f"TITLE: {title}\n"
                f"YEAR: {year}\nJOURNAL: {journal}\nDOI: {doi}\n"
                f"SOURCE: EuropePMC/{source}/{pmid}\n\n"
            )
            with open(os.path.join(PAPERS_DIR, fname), "w", encoding="utf-8") as f:
                f.write(header + content)

            meta_index.append(
                {"file": fname, "title": title, "year": year,
                 "journal": journal, "doi": doi, "pmid": pmid}
            )
            saved += 1
            print(f"[{saved}/{count}] {title[:60]}")

        cursor = data.get("nextCursorMark")
        if not cursor or cursor == params["cursorMark"]:
            break

    with open(os.path.join(PAPERS_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(meta_index, f, ensure_ascii=False, indent=2)
    print(f"\n完了: {saved}本の論文を {PAPERS_DIR} に保存しました")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=150)
    args = ap.parse_args()
    search(args.count)
