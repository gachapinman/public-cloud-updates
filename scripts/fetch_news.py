#!/usr/bin/env python3
"""
fetch_news.py
各クラウドベンダーの公式ページ対応 RSS フィードを取得し、data/news.json を更新するスクリプト。

対応ページ:
  Azure : https://azure.microsoft.com/ja-jp/updates/
  AWS   : https://aws.amazon.com/jp/new/
  GCP   : https://docs.cloud.google.com/release-notes
  OCI   : https://docs.oracle.com/en-us/iaas/releasenotes/
"""

import json
import os
import re
from datetime import datetime, timezone, timedelta
import feedparser

# ===== 設定 =====
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "news.json")
MAX_ITEMS_PER_CLOUD = 6    # 1クラウドあたり表示件数
MAX_FETCH_ENTRIES = 100    # RSSから取得する最大エントリ数（日付降順ソート用）

# RSS フィード定義（各クラウドの指定公式ページに対応するフィード）
FEEDS = {
    "azure": {
        "name": "Microsoft Azure",
        # https://azure.microsoft.com/ja-jp/updates/ の公式フィード
        "url": "https://azure.microsoft.com/ja-jp/updates/feed/",
        "fallback_url": "https://azurecomcdn.azureedge.net/ja-jp/updates/feed/",
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
        # https://docs.oracle.com/en-us/iaas/releasenotes/ の公式フィード
        "url": "https://docs.oracle.com/en-us/iaas/releasenotes/rss/whatsnew.xml",
        "fallback_url": "https://blogs.oracle.com/cloud-infrastructure/rss",
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


def main():
    JST = timezone(timedelta(hours=9))
    now_str = datetime.now(JST).strftime("%Y年%m月%d日 %H:%M JST")
    news = {
        "updated": now_str,
        "clouds": {}
    }

    for cloud_key, conf in FEEDS.items():
        print(f"Fetching {conf['name']} ...")
        items = fetch_feed(cloud_key, conf)
        news["clouds"][cloud_key] = items

    # 出力先ディレクトリを作成
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)

    print(f"\n✓ data/news.json を更新しました ({now_str})")


if __name__ == "__main__":
    main()
