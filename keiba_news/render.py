"""集計結果から 1 枚の HTML ページを作る。

出力は claude.ai の Artifact としてそのまま公開でき、ブラウザで直接開いても表示できる。
外部への通信は Google Fonts だけで、データはページ内に埋め込む。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from html import escape

_JST = timezone(timedelta(hours=9))

GRADE_CLASS = {"G1": "g1", "J・G1": "g1", "G2": "g2", "G3": "g3"}


def _fmt_jst(iso: str, fmt: str = "%m/%d %H:%M") -> str:
    return datetime.fromisoformat(iso).astimezone(_JST).strftime(fmt)


def _bar_rows(items: list[dict], empty: str) -> str:
    if not items:
        return f'<p class="empty">{escape(empty)}</p>'
    top = max(i["count"] for i in items)
    rows = []
    for i in items:
        pct = round(i["count"] / top * 100)
        rows.append(
            f'<li><span class="nm">{escape(i["name"])}</span>'
            f'<span class="track"><span class="fill" style="width:{pct}%"></span></span>'
            f'<span class="ct">{i["count"]}</span></li>'
        )
    return '<ol class="bars">' + "".join(rows) + "</ol>"


def _race_cards(races: list[dict]) -> str:
    if not races:
        return '<p class="empty">この期間の見出しに重賞名は見つかりませんでした。</p>'
    cards = []
    for r in races:
        gc = GRADE_CLASS.get(r["grade"], "g3")
        status = "これから" if r["status"] == "upcoming" else "終了"
        horses = "".join(f"<li>{escape(h)}</li>" for h in r["horses"]) or '<li class="none">話題の馬はまだ少数</li>'
        links = "".join(
            f'<li><a href="{escape(a["url"])}" target="_blank" rel="noopener">{escape(a["title"])}</a>'
            f'<span class="meta">{escape(a["source"])} · {_fmt_jst(a["published"])}</span></li>'
            for a in r["articles"][:3]
        )
        cards.append(f"""
<article class="race {r['status']}">
  <header>
    <span class="grade {gc}">{escape(r['grade'])}</span>
    <h3>{escape(r['name'])}</h3>
    <span class="status">{status}</span>
  </header>
  <dl class="counts">
    <div><dt>記事</dt><dd>{r['count']}</dd></div>
    <div><dt>予想</dt><dd>{r['yoso']}</dd></div>
    <div><dt>展望</dt><dd>{r['tenbo']}</dd></div>
    <div><dt>結果</dt><dd>{r['kekka']}</dd></div>
  </dl>
  <p class="label">見出しによく出る馬</p>
  <ul class="chips">{horses}</ul>
  <ul class="links">{links}</ul>
</article>""")
    return '<div class="races">' + "".join(cards) + "</div>"


def _daily_chart(daily: list[dict]) -> str:
    top = max([d["count"] for d in daily] + [1])
    cols = []
    for d in daily:
        h = round(d["count"] / top * 100)
        cols.append(
            f'<div class="col"><span class="v">{d["count"]}</span>'
            f'<span class="b" style="height:{max(h, 2)}%"></span><span class="d">{d["day"]}</span></div>'
        )
    return '<div class="daily" role="img" aria-label="日別の記事数">' + "".join(cols) + "</div>"


def render(summary: dict, articles: list[dict]) -> str:
    days = summary["days"]
    since = (datetime.fromisoformat(summary["generated"]) - timedelta(days=days)).isoformat()
    listed = [
        {k: a[k] for k in ("title", "url", "source", "published", "category")}
        | {"races": [r["name"] for r in a["races"]]}
        for a in articles
        if a["published"] >= since
    ]
    cats = [c for c in summary["categories"]]
    cat_chips = "".join(
        f'<button type="button" class="chip" data-cat="{c["key"]}" aria-pressed="false">'
        f'{escape(c["label"])}<span>{c["count"]}</span></button>'
        for c in cats
    )
    cat_mix = "".join(
        f'<span class="seg c-{c["key"]}" style="flex-grow:{c["count"]}" title="{escape(c["label"])} {c["count"]}件"></span>'
        for c in cats if c["count"]
    )
    cat_legend = "".join(
        f'<li><i class="dot c-{c["key"]}"></i>{escape(c["label"])} <b>{c["count"]}</b></li>' for c in cats
    )
    labels = {c["key"]: c["label"] for c in cats}
    data_json = json.dumps({"articles": listed, "labels": labels}, ensure_ascii=False).replace("</", "<\\/")
    generated = _fmt_jst(summary["generated"], "%Y年%m月%d日 %H:%M")

    return TEMPLATE.format(
        generated=generated,
        days=days,
        total_recent=summary["total_recent"],
        total_24h=summary["total_24h"],
        sources=summary["sources"],
        race_count=len(summary["races"]),
        daily=_daily_chart(summary["daily"]),
        cat_mix=cat_mix,
        cat_legend=cat_legend,
        races=_race_cards(summary["races"]),
        jockeys=_bar_rows(summary["jockeys"], "騎手名を含む見出しはまだありません。"),
        horses=_bar_rows(summary["horses"], "2 件以上の見出しに出た馬はまだいません。"),
        trainers=_bar_rows(summary["trainers"], "2 件以上の見出しに出た調教師はまだいません。"),
        cat_chips=cat_chips,
        data_json=data_json,
    )


TEMPLATE = """<meta charset="utf-8">
<title>競馬ニュースウォッチ</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Dela+Gothic+One&family=Zen+Kaku+Gothic+New:wght@400;500;700&family=IBM+Plex+Mono:wght@500&display=swap">
<style>
/* レイアウト: 上に要約（日別本数・カテゴリ構成）、中段に重賞カード、下に騎手/馬ランキングと全記事リスト */
:root {{
  --bg: #f4f6f2; --surface: #ffffff; --ink: #18211c; --muted: #5d6a62; --line: #d9e0d9;
  --turf: #1f6b45; --turf-soft: #e1efe6; --dirt: #a8742c;
  --g1: #b3261e; --g2: #1d4f91; --g3: #2f7d4a;
  --c-yoso: #a8742c; --c-tenbo: #1f6b45; --c-kekka: #1d4f91; --c-hito: #7a4e9a; --c-intai: #6b6f6c; --c-other: #b8c1ba;
  --display: "Dela Gothic One", "Hiragino Kaku Gothic StdN", "Yu Gothic", sans-serif;
  --body: "Zen Kaku Gothic New", "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #111613; --surface: #19201c; --ink: #e6ece7; --muted: #9aa69f; --line: #2c3631;
  --turf: #5fbf8a; --turf-soft: #1d3127; --dirt: #d9a65c;
  --g1: #f2776d; --g2: #7fa9e6; --g3: #6cc58c;
  --c-yoso: #d9a65c; --c-tenbo: #5fbf8a; --c-kekka: #7fa9e6; --c-hito: #b993d6; --c-intai: #9aa09c; --c-other: #4a554e;
  color-scheme: dark;
}} }}
:root[data-theme="dark"] {{
  --bg: #111613; --surface: #19201c; --ink: #e6ece7; --muted: #9aa69f; --line: #2c3631;
  --turf: #5fbf8a; --turf-soft: #1d3127; --dirt: #d9a65c;
  --g1: #f2776d; --g2: #7fa9e6; --g3: #6cc58c;
  --c-yoso: #d9a65c; --c-tenbo: #5fbf8a; --c-kekka: #7fa9e6; --c-hito: #b993d6; --c-intai: #9aa09c; --c-other: #4a554e;
  color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 15px; line-height: 1.6; margin: 0; }}
.wrap {{ max-width: 1120px; margin: 0 auto; padding-block: 28px 56px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 36px; }}
h1, h2, h3 {{ text-wrap: balance; margin: 0; }}
h1 {{ font-family: var(--display); font-weight: 400; font-size: clamp(28px, 5vw, 44px); letter-spacing: .02em; line-height: 1.15; }}
h2 {{ font-size: 18px; font-weight: 700; display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 10px; }}
h2 small {{ font-size: 12px; color: var(--muted); font-weight: 500; }}
a {{ color: inherit; text-decoration-color: var(--line); text-underline-offset: 3px; }}
a:hover {{ text-decoration-color: var(--turf); }}
a:focus-visible, button:focus-visible, input:focus-visible {{ outline: 2px solid var(--turf); outline-offset: 2px; }}
.num {{ font-family: var(--mono); font-variant-numeric: tabular-nums; }}

.top {{ display: grid; gap: 6px; border-bottom: 3px solid var(--ink); padding-bottom: 18px; }}
.top .eyebrow {{ font-size: 12px; letter-spacing: .12em; color: var(--turf); font-weight: 700; }}
.top p {{ margin: 0; color: var(--muted); }}

.summary {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.3fr); gap: 28px; align-items: start; }}
.stats {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0; border-top: 1px solid var(--line); }}
.stat {{ padding: 14px 4px; border-bottom: 1px solid var(--line); }}
.stat dt {{ font-size: 12px; color: var(--muted); }}
.stat dd {{ margin: 0; font-family: var(--mono); font-size: 30px; line-height: 1.2; font-variant-numeric: tabular-nums; }}
.stat dd small {{ font-size: 13px; color: var(--muted); font-family: var(--body); margin-left: 4px; }}
.panel {{ display: grid; gap: 14px; min-width: 0; }}
.daily {{ display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: 6px; height: 140px; align-items: end;
  border-bottom: 1px solid var(--line); padding-top: 18px; }}
.daily .col {{ display: grid; grid-template-rows: auto 1fr auto; height: 100%; align-items: end; justify-items: center; }}
.daily .v {{ font-family: var(--mono); font-size: 11px; color: var(--muted); }}
.daily .b {{ width: 100%; max-width: 34px; background: var(--turf); border-radius: 3px 3px 0 0; align-self: end; }}
.daily .col:last-child .b {{ background: var(--dirt); }}
.daily .d {{ font-family: var(--mono); font-size: 11px; color: var(--muted); padding-top: 4px; transform: translateY(100%); margin-top: -2px; }}
.mix {{ display: flex; height: 12px; border-radius: 6px; overflow: hidden; gap: 2px; margin-top: 18px; }}
.mix .seg {{ flex-basis: 0; min-width: 4px; }}
.legend {{ list-style: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--muted); }}
.legend b {{ color: var(--ink); font-family: var(--mono); font-weight: 500; }}
.dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; vertical-align: 0; }}
.c-yoso {{ background: var(--c-yoso); }} .c-tenbo {{ background: var(--c-tenbo); }} .c-kekka {{ background: var(--c-kekka); }}
.c-hito {{ background: var(--c-hito); }} .c-intai {{ background: var(--c-intai); }} .c-other {{ background: var(--c-other); }}

.races {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr)); gap: 16px; }}
.race {{ background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px; display: grid; gap: 10px; align-content: start; min-width: 0; }}
.race.finished {{ opacity: .82; }}
.race header {{ display: flex; align-items: center; gap: 10px; }}
.race h3 {{ font-size: 17px; flex: 1; min-width: 0; }}
.grade {{ font-family: var(--mono); font-size: 12px; padding: 2px 8px; border-radius: 4px; color: var(--surface); white-space: nowrap; }}
.grade.g1 {{ background: var(--g1); }} .grade.g2 {{ background: var(--g2); }} .grade.g3 {{ background: var(--g3); }}
.status {{ font-size: 12px; color: var(--muted); border: 1px solid var(--line); border-radius: 999px; padding: 1px 8px; white-space: nowrap; }}
.race.upcoming .status {{ color: var(--turf); border-color: var(--turf); background: var(--turf-soft); }}
.counts {{ display: grid; grid-template-columns: repeat(4, 1fr); margin: 0; border-block: 1px solid var(--line); }}
.counts div {{ padding: 6px 0; text-align: center; }}
.counts dt {{ font-size: 11px; color: var(--muted); }}
.counts dd {{ margin: 0; font-family: var(--mono); font-size: 18px; font-variant-numeric: tabular-nums; }}
.label {{ margin: 0; font-size: 12px; color: var(--muted); }}
.chips {{ list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }}
.chips li {{ font-size: 13px; padding: 2px 10px; border-radius: 999px; background: var(--turf-soft); color: var(--ink); }}
.chips li.none {{ background: none; color: var(--muted); padding-left: 0; }}
.links {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; font-size: 13px; }}
.links li {{ display: grid; gap: 1px; }}
.meta {{ font-size: 11px; color: var(--muted); }}

.ranks {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 28px; }}
.bars {{ list-style: none; margin: 10px 0 0; padding: 0; display: grid; gap: 6px; counter-reset: r; }}
.bars li {{ display: grid; grid-template-columns: 1.6em minmax(5em, 9em) 1fr 2.4em; align-items: center; gap: 8px; font-size: 14px; counter-increment: r; }}
.bars li::before {{ content: counter(r); font-family: var(--mono); font-size: 12px; color: var(--muted); text-align: right; }}
.bars .nm {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.bars .track {{ height: 8px; background: var(--line); border-radius: 4px; overflow: hidden; }}
.bars .fill {{ display: block; height: 100%; background: var(--turf); }}
.bars .ct {{ font-family: var(--mono); font-size: 13px; text-align: right; font-variant-numeric: tabular-nums; }}
.empty {{ color: var(--muted); font-size: 13px; margin: 10px 0 0; }}

.feed-tools {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
.chip {{ font: inherit; font-size: 13px; border: 1px solid var(--line); background: var(--surface); color: var(--ink); border-radius: 999px; padding: 4px 12px; cursor: pointer; display: inline-flex; gap: 6px; }}
.chip span {{ font-family: var(--mono); color: var(--muted); }}
.chip[aria-pressed="true"] {{ background: var(--ink); color: var(--bg); border-color: var(--ink); }}
.chip[aria-pressed="true"] span {{ color: var(--bg); }}
#q {{ font: inherit; font-size: 14px; flex: 1 1 200px; min-width: 0; padding: 6px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); color: var(--ink); }}
.feed {{ list-style: none; margin: 0; padding: 0; }}
.feed .day {{ font-family: var(--mono); font-size: 12px; color: var(--muted); padding: 18px 0 6px; border-bottom: 1px solid var(--ink); }}
.feed .item {{ display: grid; grid-template-columns: 4.5em 1fr; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--line); }}
.feed .item time {{ font-family: var(--mono); font-size: 12px; color: var(--muted); padding-top: 2px; }}
.feed .item div {{ min-width: 0; display: grid; gap: 2px; }}
.feed .tag {{ font-size: 11px; color: var(--muted); }}
.feed .tag i {{ margin-right: 4px; }}
.count-note {{ font-size: 13px; color: var(--muted); }}
footer {{ font-size: 12px; color: var(--muted); border-top: 1px solid var(--line); padding-top: 14px; }}
footer p {{ margin: 0 0 4px; }}

@media (max-width: 820px) {{
  .summary {{ grid-template-columns: 1fr; }}
  .ranks {{ grid-template-columns: 1fr; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
</style>

<div class="wrap">
  <header class="top">
    <span class="eyebrow">JRA 中央競馬 · ニュース定点観測</span>
    <h1>競馬ニュースウォッチ</h1>
    <p>{generated} 更新 · 直近 {days} 日の見出しを集計</p>
  </header>

  <section class="summary" aria-label="概要">
    <div class="panel">
      <dl class="stats">
        <div class="stat"><dt>直近 24 時間</dt><dd>{total_24h}<small>件</small></dd></div>
        <div class="stat"><dt>直近 {days} 日</dt><dd>{total_recent}<small>件</small></dd></div>
        <div class="stat"><dt>配信元</dt><dd>{sources}<small>媒体</small></dd></div>
        <div class="stat"><dt>話題の重賞</dt><dd>{race_count}<small>レース</small></dd></div>
      </dl>
    </div>
    <div class="panel">
      <h2>日別の記事数 <small>日本時間・最終日は集計途中</small></h2>
      {daily}
      <div class="mix" aria-hidden="true">{cat_mix}</div>
      <ul class="legend">{cat_legend}</ul>
    </div>
  </section>

  <section class="panel" aria-labelledby="h-races">
    <h2 id="h-races">重賞ごとの話題 <small>予想・展望が結果より多いレースを「これから」としています</small></h2>
    {races}
  </section>

  <section class="ranks" aria-label="ランキング">
    <div><h2>見出しに出た騎手</h2>{jockeys}</div>
    <div><h2>話題の馬 <small>候補</small></h2>{horses}</div>
    <div><h2>見出しに出た調教師</h2>{trainers}</div>
  </section>

  <section class="panel" aria-labelledby="h-feed">
    <h2 id="h-feed">記事一覧</h2>
    <div class="feed-tools">
      <input id="q" type="search" placeholder="馬名・レース名・騎手で絞り込み" aria-label="記事を絞り込む">
      {cat_chips}
    </div>
    <p class="count-note" id="count-note"></p>
    <ul class="feed" id="feed"></ul>
  </section>

  <footer>
    <p>出典: Google ニュースの検索結果（各記事は配信元のサイトで読めます）。見出しだけを機械的に分類しているため、誤分類や馬名の拾い漏れがあります。</p>
    <p>「話題の馬」は 2 件以上の見出しに出たカタカナ語から、レース名や騎手名などを除いた候補です。</p>
  </footer>
</div>

<script id="data" type="application/json">{data_json}</script>
<script>
(function () {{
  var data = JSON.parse(document.getElementById("data").textContent);
  var feed = document.getElementById("feed");
  var q = document.getElementById("q");
  var note = document.getElementById("count-note");
  var chips = Array.prototype.slice.call(document.querySelectorAll(".chip"));
  var active = null;
  var fmtDay = new Intl.DateTimeFormat("ja-JP", {{ timeZone: "Asia/Tokyo", month: "long", day: "numeric", weekday: "short" }});
  var fmtTime = new Intl.DateTimeFormat("ja-JP", {{ timeZone: "Asia/Tokyo", hour: "2-digit", minute: "2-digit" }});
  function el(tag, cls, text) {{ var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }}
  function draw() {{
    var term = q.value.trim().toLowerCase();
    var rows = data.articles.filter(function (a) {{
      if (active && a.category !== active) return false;
      if (!term) return true;
      return (a.title + " " + a.source + " " + a.races.join(" ")).toLowerCase().indexOf(term) !== -1;
    }});
    feed.textContent = "";
    var last = "";
    rows.forEach(function (a) {{
      var d = new Date(a.published);
      var day = fmtDay.format(d);
      if (day !== last) {{ feed.appendChild(el("li", "day", day)); last = day; }}
      var li = el("li", "item");
      li.appendChild(el("time", null, fmtTime.format(d)));
      var box = el("div");
      var link = el("a", null, a.title); link.href = a.url; link.target = "_blank"; link.rel = "noopener";
      box.appendChild(link);
      var tag = el("span", "tag");
      var dot = el("i", "dot c-" + a.category); tag.appendChild(dot);
      tag.appendChild(document.createTextNode((data.labels[a.category] || "") + " · " + a.source));
      box.appendChild(tag);
      li.appendChild(box);
      feed.appendChild(li);
    }});
    note.textContent = rows.length + " 件を表示" + (rows.length ? "" : "。条件に合う記事はありません。絞り込みを解除してください。");
  }}
  chips.forEach(function (c) {{
    c.addEventListener("click", function () {{
      active = active === c.dataset.cat ? null : c.dataset.cat;
      chips.forEach(function (x) {{ x.setAttribute("aria-pressed", String(x.dataset.cat === active)); }});
      draw();
    }});
  }});
  q.addEventListener("input", draw);
  draw();
}})();
</script>
"""
