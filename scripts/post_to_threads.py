#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
楽天ランキングAPIから商品を取得し、テンプレートで紹介文を生成して
Typefullyに「下書き」として登録するスクリプト。
Typefully側のスケジュール投稿機能で21時に自動公開される想定。

必要な環境変数(GitHub Secretsから渡される):
  RAKUTEN_APP_ID        楽天アプリID
  RAKUTEN_AFFILIATE_ID  楽天アフィリエイトID
  RAKUTEN_ACCESS_KEY    楽天アクセスキー(現状未使用だが将来のため保持)
  TYPEFULLY_API_KEY     Typefully APIキー
  MY_REGISTERED_URL     登録済みの自分のサイトURL(必要に応じ利用)
"""

import os
import sys
import random
import datetime
import requests

RAKUTEN_APP_ID = os.environ["RAKUTEN_APP_ID"]
RAKUTEN_AFFILIATE_ID = os.environ["RAKUTEN_AFFILIATE_ID"]
TYPEFULLY_API_KEY = os.environ["TYPEFULLY_API_KEY"]

RAKUTEN_RANKING_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Ranking/20220601"
TYPEFULLY_DRAFTS_URL = "https://api.typefully.com/v1/drafts/"

# 曜日ごとのジャンルローテーション(0=月曜 ... 6=日曜)
# ジャンルIDは楽天ジャンル検索APIで確認・変更可能
GENRE_ROTATION = {
    0: {"id": "100804", "name": "家電"},
    1: {"id": "100939", "name": "コスメ・美容"},
    2: {"id": "100227", "name": "食品"},
    3: {"id": "100804", "name": "生活雑貨"},  # TODO: 適切なジャンルIDに要調整
    4: {"id": "101070", "name": "ファッション"},
    5: {"id": "101164", "name": "スポーツ・アウトドア"},
    6: {"id": "101205", "name": "ホビー・おもちゃ"},
}

TEMPLATE = """本日の楽天ランキング1位はコレ!
「{item_name}」

{catch_copy}

▼詳細はこちら
{affiliate_url}

#PR #楽天 #楽天ランキング #{genre_name}"""


def fetch_ranking_item(genre_id: str) -> dict:
    """指定ジャンルの楽天ランキング1位商品を取得する"""
    params = {
        "format": "json",
        "genreId": genre_id,
        "applicationId": RAKUTEN_APP_ID,
        "affiliateId": RAKUTEN_AFFILIATE_ID,
        "period": "realtime",
    }
    res = requests.get(RAKUTEN_RANKING_URL, params=params, timeout=15)
    res.raise_for_status()
    data = res.json()

    items = data.get("Items", [])
    if not items:
        raise RuntimeError(f"ジャンルID {genre_id} のランキング結果が空です")

    return items[0]["Item"]


def build_post_text(item: dict, genre_name: str) -> str:
    """テンプレートに商品情報を差し込んで投稿文を作る"""
    item_name = item.get("itemName", "").strip()
    catch_copy = item.get("catchcopy", "").strip()
    affiliate_url = item.get("affiliateUrl") or item.get("itemUrl")

    # Threadsの文字数制限(500文字)を考慮して商品名を適度に切る
    if len(item_name) > 60:
        item_name = item_name[:60] + "…"

    return TEMPLATE.format(
        item_name=item_name,
        catch_copy=catch_copy or "楽天ランキング上位の人気商品です。",
        affiliate_url=affiliate_url,
        genre_name=genre_name,
    )


def create_typefully_draft(content: str, schedule_date_iso: str) -> dict:
    """Typefullyに下書き(スケジュール指定)を作成する"""
    headers = {
        "X-API-KEY": TYPEFULLY_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "content": content,
        "threadify": False,
        "schedule-date": schedule_date_iso,
        "share": False,
    }
    res = requests.post(TYPEFULLY_DRAFTS_URL, json=payload, headers=headers, timeout=15)
    if not res.ok:
        raise RuntimeError(f"Typefully API エラー: {res.status_code} {res.text}")
    return res.json()


def main():
    # JST基準の曜日を使う(GitHub Actionsのランナーは通常UTC)
    now_jst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    weekday = now_jst.weekday()
    genre = GENRE_ROTATION[weekday]

    print(f"[INFO] 今日の曜日: {weekday} / ジャンル: {genre['name']} (ID: {genre['id']})")

    item = fetch_ranking_item(genre["id"])
    text = build_post_text(item, genre["name"])
    print("[INFO] 生成した投稿文:")
    print(text)

    # 本日21:00 JST を Typefully に渡すISO日時に変換(UTC表記)
    schedule_dt_jst = now_jst.replace(hour=21, minute=0, second=0, microsecond=0)
    schedule_dt_utc = schedule_dt_jst - datetime.timedelta(hours=9)
    schedule_iso = schedule_dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    result = create_typefully_draft(text, schedule_iso)
    print("[INFO] Typefully下書き作成完了:")
    print(result)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
