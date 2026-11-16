"""見出しを分類し、レース・騎手・馬の話題量を集計する。"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from . import config
from .races import build_race_patterns

_RACE_PATTERNS = build_race_patterns()
# 漢字だけ・カタカナだけの名前に分けて、馬名と騎手名がつながる誤検出を防ぐ
_JOCKEY_RE = re.compile(r"(?:([一-龥々]{2,4})|([ァ-ヶー]{2,8}))騎手")
_TRAINER_RE = re.compile(r"([一-龥々]{2,4})調教師")
_KATAKANA_RE = re.compile(r"[ァ-ヶー]{3,9}")
_JST = timezone(timedelta(hours=9))


def classify(title: str) -> tuple[str, list[str]]:
    tags = [key for key, _label, words in config.CATEGORIES if any(w in title for w in words)]
    primary = tags[0] if tags else config.OTHER_CATEGORY[0]
    return primary, tags


def find_races(title: str) -> list[tuple[str, str]]:
    """見出しに出てくる重賞を (正式名, グレード) で、出てきた順に返す。

    重なった表記は長い方を優先する。先頭のレースがその記事の主題になることが多い。
    """
    taken = [False] * len(title)
    hits: dict[tuple[str, str], int] = {}
    for alias, name, grade in _RACE_PATTERNS:
        start = 0
        while (i := title.find(alias, start)) != -1:
            end = i + len(alias)
            # "オークス馬" "ダービー馬" は勝ち馬を指すので主題にしない
            if title[end:end + 1] == "馬":
                start = end
                continue
            if not any(taken[i:end]):
                for k in range(i, end):
                    taken[k] = True
                key = (name, grade)
                hits[key] = min(hits.get(key, i), i)
            start = end
    return sorted(hits, key=hits.get)


def find_jockeys(title: str) -> list[str]:
    names = []
    for m in _JOCKEY_RE.finditer(title):
        n = m.group(1) or m.group(2)
        if n in config.JOCKEY_STOPWORDS or n in names:
            continue
        names.append(n)
    return names


def find_trainers(title: str) -> list[str]:
    names = []
    for m in _TRAINER_RE.finditer(title):
        n = m.group(1)
        if n not in names and n not in config.JOCKEY_STOPWORDS:
            names.append(n)
    return names


def find_horse_candidates(title: str, exclude: set[str]) -> list[str]:
    names = []
    for m in _KATAKANA_RE.finditer(title):
        w = m.group(0)
        if w in config.HORSE_STOPWORDS or w in exclude or w in names:
            continue
        if any(w in race for race in exclude):
            continue
        names.append(w)
    return names


def enrich(articles: list[dict]) -> list[dict]:
    race_words = {alias for alias, _n, _g in _RACE_PATTERNS}
    out = []
    for a in articles:
        title = a["title"]
        primary, tags = classify(title)
        races = find_races(title)
        jockeys = find_jockeys(title)
        exclude = race_words | set(jockeys)
        out.append(dict(
            a,
            category=primary,
            tags=tags,
            races=[{"name": n, "grade": g} for n, g in races],
            jockeys=jockeys,
            trainers=find_trainers(title),
            horses=find_horse_candidates(title, exclude),
        ))
    return out


def _race_status(items: list[dict]) -> str:
    """直近 36 時間の記事で、結果記事が予想・展望記事より多ければ「終了」とみなす。"""
    newest = datetime.fromisoformat(items[0]["published"])
    window = (newest - timedelta(hours=36)).isoformat()
    near = [a for a in items if a["published"] >= window]
    done = sum(1 for a in near if "kekka" in a["tags"])
    ahead = sum(1 for a in near if a["category"] in ("yoso", "tenbo"))
    return "finished" if done > ahead else "upcoming"


def _within(a: dict, since: datetime) -> bool:
    return a["published"] >= since.isoformat()


def summarize(articles: list[dict], now: datetime | None = None, days: int = 7) -> dict:
    """ページに載せる集計をまとめて作る。articles は enrich 済みであること。"""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    recent = [a for a in articles if _within(a, since)]
    last24 = [a for a in articles if _within(a, now - timedelta(hours=24))]

    labels = {k: label for k, label, _w in config.CATEGORIES}
    labels[config.OTHER_CATEGORY[0]] = config.OTHER_CATEGORY[1]
    by_cat = Counter(a["category"] for a in recent)

    # レース別：見出しの主題（最初に出てくる重賞）だけを数える
    race_info: dict[str, dict] = {}
    race_items: dict[str, list[dict]] = defaultdict(list)
    for a in recent:
        if not a["races"]:
            continue
        r = a["races"][0]
        info = race_info.setdefault(r["name"], {
            "name": r["name"], "grade": r["grade"], "count": 0,
            "yoso": 0, "tenbo": 0, "kekka": 0, "latest": a["published"], "articles": [],
        })
        info["count"] += 1
        for t in ("yoso", "tenbo", "kekka"):
            if t in a["tags"]:
                info[t] += 1
        info["latest"] = max(info["latest"], a["published"])
        race_items[r["name"]].append(a)

    races = []
    for name, info in race_info.items():
        items = sorted(race_items[name], key=lambda a: a["published"], reverse=True)
        info["status"] = _race_status(items)
        info["articles"] = [
            {k: a[k] for k in ("title", "url", "source", "published", "category")} for a in items[:6]
        ]
        horses = Counter(h for a in items for h in a["horses"])
        info["horses"] = [h for h, c in horses.most_common(6) if c >= 2]
        races.append(info)
    grade_rank = {"G1": 0, "J・G1": 1, "G2": 2, "G3": 3}
    races.sort(key=lambda r: (r["status"] != "upcoming", -r["count"], grade_rank.get(r["grade"], 9)))

    jockeys = Counter(j for a in recent for j in a["jockeys"])
    trainers = Counter(t for a in recent for t in a["trainers"])
    horses = Counter(h for a in recent for h in a["horses"])

    # 日別件数（JST）
    daily = Counter()
    for a in recent:
        d = datetime.fromisoformat(a["published"]).astimezone(_JST).strftime("%m/%d")
        daily[d] += 1
    day_axis = [(now - timedelta(days=i)).astimezone(_JST).strftime("%m/%d") for i in range(days - 1, -1, -1)]

    return {
        "generated": now.isoformat(),
        "days": days,
        "total_recent": len(recent),
        "total_24h": len(last24),
        "sources": len({s for a in recent for s in a.get("sources", [a["source"]])}),
        "categories": [
            {"key": k, "label": labels[k], "count": by_cat.get(k, 0)}
            for k in [*labels.keys()]
        ],
        # 1 本だけの言及は過去レースへの言及であることが多いので外す
        "races": [r for r in races if r["count"] >= 2][:12],
        "jockeys": [{"name": n, "count": c} for n, c in jockeys.most_common(10) if c >= 2],
        "trainers": [{"name": n, "count": c} for n, c in trainers.most_common(8) if c >= 2],
        "horses": [{"name": n, "count": c} for n, c in horses.most_common(15) if c >= 2],
        "daily": [{"day": d, "count": daily.get(d, 0)} for d in day_axis],
    }
