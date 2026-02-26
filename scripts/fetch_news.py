#!/usr/bin/env python3
"""
fetch_news.py
各クラウドベンダーの公式ページ対応 RSS フィードを取得し、data/news.json を更新するスクリプト。

対応ページ:
  Azure : https://azure.microsoft.com/ja-jp/updates/  (RSS: https://www.microsoft.com/releasecommunications/api/v2/azure/rss)
  AWS   : https://aws.amazon.com/jp/new/
  GCP   : https://docs.cloud.google.com/release-notes
  OCI   : https://docs.oracle.com/en-us/iaas/releasenotes/
"""

import json
import os
import re
import urllib.request
from datetime import datetime, timezone, timedelta
import feedparser

# ===== 設定 =====
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "news.json")
MAX_ITEMS_PER_CLOUD = 20   # 1クラウドあたり保存件数（UI側で表示件数を制御）
MAX_FETCH_ENTRIES = 100    # RSSから取得する最大エントリ数（日付降順ソート用）

# RSS フィード定義（各クラウドの指定公式ページに対応するフィード）
FEEDS = {
    "azure": {
        "name": "Microsoft Azure",
        # https://azure.microsoft.com/ja-jp/updates/ の公式フィード（RSSボタンのリンク先）
        "url": "https://www.microsoft.com/releasecommunications/api/v2/azure/rss",
        "fallback_url": "https://azurecomcdn.azureedge.net/en-us/updates/feed/",
    },
    "aws": {
        "name": "Amazon Web Services",
        # https://aws.amazon.com/jp/new/ の公式フィード
        "url": "https://aws.amazon.com/jp/new/feed/",
        "fallback_url": "https://aws.amazon.com/new/feed/",
    },
    "gcp": {
        "name": "Google Cloud Platform",
        # https://docs.cloud.google.com/release-notes の公式フィード
        "url": "https://cloud.google.com/feeds/gcp-release-notes.xml",
        "fallback_url": "https://cloudblog.withgoogle.com/products/gcp/rss/",
    },
    "oci": {
        "name": "Oracle Cloud Infrastructure",
        # OCI には RSS フィードがないためウェブスクレイピングで取得
        "url": "https://docs.oracle.com/en-us/iaas/releasenotes/",
        "scrape": True,
    },
}

# カテゴリ判定キーワード (順番が優先順位) — 英語 + 日本語
CATEGORY_RULES = [
    ("ai-tag",       ["ai", "ml", "machine learning", "generative", "llm", "bedrock",
                       "sagemaker", "vertex", "foundry", "openai", "gemini", "gpt",
                       "phi", "llama", "diffusion", "inference", "training", "neural",
                       # 日本語
                       "人工知能", "生成ai", "機械学習", "推論", "学習モデル", "エージェント",
                       "チャット", "言語モデル", "ベクター検索", "ファインチューニング"]),
    ("security-tag", ["security", "iam", "identity", "auth", "mfa", "zero trust",
                       "compliance", "encryption", "kms", "vault", "sentinel",
                       "defender", "guard", "waf", "shield", "entra",
                       # 日本語
                       "セキュリティ", "認証", "暗号化", "ゼロトラスト", "アイデンティティ",
                       "コンプライアンス", "権限管理", "不正アクセス", "脆弱性", "脚威脅迫"]),
    ("container-tag",["kubernetes", "container", "eks", "aks", "gke", "oke",
                       "docker", "helm", "fargate", "cloud run", "app service",
                       # 日本語
                       "コンテナ", "クバネティス", "コンテナイメージ", "マイクロサービス"]),
    ("database-tag", ["database", "db", "rds", "aurora", "dynamo", "cosmos", "spanner",
                       "alloydb", "sql", "postgres", "mysql", "redis", "mongodb",
                       "autonomous", "heatwave", "bigtable", "firestore",
                       # 日本語
                       "データベース", "データウェアハウス", "データ分析", "データウェア",
                       "ベクターデータベース", "ビッグクエリ", "ストリーミング分析"]),
    ("storage-tag",  ["storage", "s3", "blob", "bucket", "gcs", "object storage",
                       "efs", "fsx", "archive", "backup",
                       # 日本語
                       "ストレージ", "バックアップ", "アーカイブ", "オブジェクトストレージ",
                       "ファイルストレージ", "ブロックストレージ"]),
    ("network-tag",  ["network", "vpc", "vnet", "subnet", "cdn", "cloudfront",
                       "load balancer", "dns", "route", "direct connect",
                       "expressroute", "vpn", "firewall",
                       # 日本語
                       "ネットワーク", "ファイアウォール", "ロードバランサー",
                       "コンテンツ配信", "専用線", "vpn接続", "サブネット"]),
    ("compute-tag",  ["compute", "ec2", "vm", "virtual machine", "instance",
                       "graviton", "cobalt", "axion", "ampere", "gpu", "tpu",
                       "lambda", "functions", "serverless", "batch",
                       # 日本語
                       "仒想マシン", "コンピューティング", "サーバーレス", "バッチ処理",
                       "高性能コンピューティング", "hpc", "インスタンス", "gpuクラスター"]),
]


def detect_category(title: str, summary: str) -> str:
    """タイトルとサマリーからカテゴリを推定する"""
    text = (title + " " + summary).lower()
    for tag, keywords in CATEGORY_RULES:
        if any(kw in text for kw in keywords):
            return tag
    return "compute-tag"  # デフォルト


def detect_category_label(tag: str) -> str:
    """タグ名から表示ラベルへの変換"""
    labels = {
        "ai-tag":        "AI / ML",
        "security-tag":  "セキュリティ",
        "container-tag": "コンテナ",
        "database-tag":  "データベース",
        "storage-tag":   "ストレージ",
        "network-tag":   "ネットワーク",
        "compute-tag":   "コンピューティング",
    }
    return labels.get(tag, "その他")


def parse_date(entry) -> tuple[str, str]:
    """
    フィードエントリから日付を解析し、
    (display_str: "YYYY年M月D日", iso_str: "YYYY-MM-DD") を返す
    """
    JST = timezone(timedelta(hours=9))
    ts = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if ts:
        dt = datetime(*ts[:6], tzinfo=timezone.utc).astimezone(JST)
    else:
        dt = datetime.now(JST)
    return f"{dt.year}年{dt.month}月{dt.day}日", dt.strftime("%Y-%m-%d")


def clean_text(text: str, max_len: int = 180) -> str:
    """HTML タグを除去し、指定文字数に切り詰める"""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "…"
    return text


def strip_azure_prefix(title: str) -> str:
    """Azure RSS タイトルの '[Launched] ' '[In preview] ' などのプレフィックスを除去"""
    return re.sub(r"^\[(Launched|In preview|In development|Retired)\]\s*", "", title).strip()


def fetch_feed(cloud_key: str, conf: dict) -> list[dict]:
    """指定のクラウドの RSS を取得してニュースアイテムリストを返す"""
    items = []
    for url in [conf["url"], conf.get("fallback_url", "")]:
        if not url:
            continue
        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                continue  # 解析失敗
            all_entries = []
            for entry in feed.entries[:MAX_FETCH_ENTRIES]:
                title   = clean_text(entry.get("title", "(タイトルなし)"), 120)
                if cloud_key == "azure":
                    title = strip_azure_prefix(title)
                summary = clean_text(entry.get("summary", entry.get("description", "")), 200)
                link    = entry.get("link", "")
                date_display, date_iso = parse_date(entry)
                cat_tag   = detect_category(title, summary)
                cat_label = detect_category_label(cat_tag)

                all_entries.append({
                    "title":      title,
                    "link":       link,
                    "summary":    summary,
                    "date":       date_display,
                    "date_iso":   date_iso,
                    "category":   cat_tag,
                    "cat_label":  cat_label,
                    "tag":        cloud_key.upper(),
                })
            # 公開日降順ソート → 最大件数取得
            all_entries.sort(key=lambda x: x["date_iso"], reverse=True)
            items = all_entries[:MAX_ITEMS_PER_CLOUD]
            if items:
                print(f"  [{cloud_key}] {len(items)} 件取得 ({url})")
                break
        except Exception as e:
            print(f"  [{cloud_key}] 取得失敗 ({url}): {e}")
    return items


def fetch_aws_from_web() -> list[dict]:
    """AWS What's New ページをスクレイピングして最新アイテムを返す（RSS フィード不具合時のフォールバック）"""
    url = "https://aws.amazon.com/jp/about-aws/whats-new/recent/"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [aws] ページ取得失敗: {e}")
        return []

    JST = timezone(timedelta(hours=9))
    items = []
    seen_slugs = set()

    # --- パース戦略 1: <a> タグから whats-new 記事リンクとタイトルを抽出 ---
    # AWS ページの HTML 構造: <a href="/about-aws/whats-new/YYYY/MM/slug">タイトル</a>
    link_pattern = re.compile(
        r'<a\s[^>]*href="((?:https://aws\.amazon\.com)?/(?:jp/)?about-aws/whats-new/(\d{4})/(\d{2})/([^"/?#]+))[^"]*"[^>]*>'
        r'([^<]+)</a>',
        re.IGNORECASE
    )

    for m in link_pattern.finditer(html):
        raw_link = m.group(1)
        year = m.group(2)
        month = m.group(3)
        slug = m.group(4).strip().rstrip("/")
        title = m.group(5).strip()

        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        title = clean_text(title, 120)
        if not title or len(title) < 5:
            continue

        # URL を正規化（日本語ページに揃える）
        link = f"https://aws.amazon.com/jp/about-aws/whats-new/{year}/{month}/{slug}/"

        # 日付: リンク近辺から YYYY-MM-DD パターンを検索
        date_iso = f"{year}-{month}-01"  # デフォルトは月初
        date_display = f"{year}年{int(month)}月1日"
        link_pos = m.start()
        # リンクの前後 500 文字以内で日付を探す
        search_start = max(0, link_pos - 300)
        search_end = min(len(html), m.end() + 500)
        nearby_html = html[search_start:search_end]
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', nearby_html)
        if date_match:
            date_iso = date_match.group(0)
            try:
                y = int(date_match.group(1))
                mo = int(date_match.group(2))
                d = int(date_match.group(3))
                date_display = f"{y}年{mo}月{d}日"
            except ValueError:
                pass

        cat_tag = detect_category(title, "")
        cat_label = detect_category_label(cat_tag)
        items.append({
            "title":     title,
            "link":      link,
            "summary":   "",
            "date":      date_display,
            "date_iso":  date_iso,
            "category":  cat_tag,
            "cat_label": cat_label,
            "tag":       "AWS",
        })

    # 日付降順ソートして上位 N 件を返す
    items.sort(key=lambda x: x["date_iso"], reverse=True)
    result = items[:MAX_ITEMS_PER_CLOUD]
    if result:
        print(f"  [aws] {len(result)} 件取得 (web scraping: {url})")
    else:
        print(f"  [aws] 0 件取得 (スクレイピング失敗またはアイテムなし)")
    return result


def merge_aws_items(rss_items: list[dict], web_items: list[dict]) -> list[dict]:
    """RSS とスクレイピングの結果をマージして重複を排除し、最新順に並べる"""
    seen = {}
    for item in rss_items + web_items:
        # URL のスラッグで重複判定
        slug = item["link"].rstrip("/").split("/")[-1]
        if slug not in seen or item["date_iso"] > seen[slug]["date_iso"]:
            seen[slug] = item
    merged = list(seen.values())
    merged.sort(key=lambda x: x["date_iso"], reverse=True)
    return merged[:MAX_ITEMS_PER_CLOUD]


def fetch_oci_from_web() -> list[dict]:
    """OCI リリースノートページをスクレイピングして最新アイテムを返す（RSS 廃止対応）"""
    url = "https://docs.oracle.com/en-us/iaas/releasenotes/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; cloud-news-fetcher/1.0)"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [oci] ページ取得失敗: {e}")
        return []

    JST = timezone(timedelta(hours=9))
    items = []

    # h2 タグで区切り、各ブロックからタイトル・リンク・日付を抽出
    blocks = re.split(r'<h2[^>]*>', html, flags=re.IGNORECASE)[1:]
    for block in blocks[:60]:
        # 最初の <a href> からタイトルとリンクを取得
        link_match = re.search(r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>', block)
        if not link_match:
            continue
        link = link_match.group(1).strip()
        title = clean_text(link_match.group(2))
        if not title or len(title) < 5 or '🔗' in title:
            continue
        # 相対 URL を絶対 URL に変換
        if link.startswith("/"):
            link = "https://docs.oracle.com" + link
        elif not link.startswith("http"):
            continue

        # ブロック内から Release Date を抽出
        # HTML構造: <span class="vl-relnotedate">February 20, 2026</span>
        date_match = re.search(r'vl-relnotedate">([A-Za-z]+ \d+, \d{4})', block)
        if not date_match:
            continue
        try:
            dt = datetime.strptime(date_match.group(1), "%B %d, %Y")
            date_iso = dt.strftime("%Y-%m-%d")
            date_display = f"{dt.year}年{dt.month}月{dt.day}日"
        except ValueError:
            continue

        cat_tag = detect_category(title, "")
        cat_label = detect_category_label(cat_tag)
        items.append({
            "title":     title,
            "link":      link,
            "summary":   "",
            "date":      date_display,
            "date_iso":  date_iso,
            "category":  cat_tag,
            "cat_label": cat_label,
            "tag":       "OCI",
        })

    # 日付降順ソートして上位 N 件を返す
    items.sort(key=lambda x: x["date_iso"], reverse=True)
    result = items[:MAX_ITEMS_PER_CLOUD]
    if result:
        print(f"  [oci] {len(result)} 件取得 (web scraping: {url})")
    else:
        print(f"  [oci] 0 件取得 (スクレイピング失敗またはアイテムなし)")
    return result


def main():
    JST = timezone(timedelta(hours=9))
    now_str = datetime.now(JST).strftime("%Y年%m月%d日 %H:%M JST")
    news = {
        "updated": now_str,
        "clouds": {}
    }

    for cloud_key, conf in FEEDS.items():
        print(f"Fetching {conf['name']} ...")
        if conf.get("scrape"):
            items = fetch_oci_from_web()
        elif cloud_key == "aws":
            # AWS: RSS フィードが古い場合にウェブスクレイピングでフォールバック
            rss_items = fetch_feed(cloud_key, conf)
            # RSS の最新エントリが 7 日以上前なら、スクレイピングも試行
            today = datetime.now(JST).strftime("%Y-%m-%d")
            latest_rss = rss_items[0]["date_iso"] if rss_items else "2000-01-01"
            try:
                days_old = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(latest_rss, "%Y-%m-%d")).days
            except ValueError:
                days_old = 999
            if days_old > 7:
                print(f"  [aws] RSS データが {days_old} 日前のため、ウェブスクレイピングも試行します...")
                web_items = fetch_aws_from_web()
                items = merge_aws_items(rss_items, web_items)
            else:
                items = rss_items
        else:
            items = fetch_feed(cloud_key, conf)
        news["clouds"][cloud_key] = items

    # 出力先ディレクトリを作成
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)

    print(f"\n✓ data/news.json を更新しました ({now_str})")


if __name__ == "__main__":
    main()
