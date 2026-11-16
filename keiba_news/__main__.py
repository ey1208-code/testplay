"""使い方:

    python -m keiba_news            # 収集してページを作る
    python -m keiba_news --no-fetch # 保存済みデータからページだけ作り直す
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import analyze, collect, render


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="keiba_news", description="競馬ニュースを集めて集計ページを作る")
    p.add_argument("--data", default="data/articles.json", help="記事の保存先")
    p.add_argument("--out", default="docs/index.html", help="生成する HTML")
    p.add_argument("--days", type=int, default=7, help="集計する日数")
    p.add_argument("--no-fetch", action="store_true", help="ニュースを取得せず保存済みデータだけ使う")
    args = p.parse_args(argv)

    now = datetime.now(timezone.utc)
    data_path = Path(args.data)
    if args.no_fetch:
        articles = collect.load(data_path)
    else:
        articles, stats = collect.collect(data_path, now)
        print(f"取得: {stats['queries']} クエリ / {stats['fetched']} 件 → 保存 {stats['stored']} 件")
        for err in stats["errors"]:
            print("警告:", err, file=sys.stderr)

    enriched = analyze.enrich(articles)
    summary = analyze.summarize(enriched, now, days=args.days)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render.render(summary, enriched), encoding="utf-8")
    print(f"出力: {out}（直近 {args.days} 日 {summary['total_recent']} 件、重賞 {len(summary['races'])} レース）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
