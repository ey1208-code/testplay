import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from keiba_news import analyze, collect, render

FIXTURE = (Path(__file__).parent / "fixtures" / "sample_feed.xml").read_bytes()
NOW = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)


class CleanTitleTest(unittest.TestCase):
    def test_strips_repeated_source_and_section(self):
        t = collect.clean_title("見出し本文 | 競馬ニュース - netkeiba - netkeiba", "netkeiba")
        self.assertEqual(t, "見出し本文")

    def test_strips_yahoo_suffix_and_original_media(self):
        t = collect.clean_title("見出し本文（日刊スポーツ） - Yahoo!ニュース", "Yahoo!ニュース")
        self.assertEqual(t, "見出し本文")

    def test_normalizes_full_width(self):
        self.assertEqual(collect.clean_title("マイルＣＳ　Ｇ１", ""), "マイルCS G1")


class CollectTest(unittest.TestCase):
    def test_parse_skips_bad_dates(self):
        items = collect.parse_feed(FIXTURE, "q")
        self.assertEqual(len(items), 5)

    def test_collect_dedupes_excludes_and_persists(self):
        with TemporaryDirectory() as d:
            path = Path(d) / "a.json"
            articles, stats = collect.collect(path, NOW, fetcher=lambda url: FIXTURE)
            titles = [a["title"] for a in articles]
            # netkeiba と Yahoo!の同じ見出しは 1 件にまとまる
            self.assertEqual(sum("展望" in t for t in titles), 1)
            merged = next(a for a in articles if "展望" in a["title"])
            self.assertEqual(merged["sources"], ["Yahoo!ニュース", "netkeiba"])
            # 地方競馬の記事は除外
            self.assertFalse(any("南部駒賞" in t for t in titles))
            self.assertEqual(len(articles), 3)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["articles"]), 3)
            # 2 回目は増えない
            again, _ = collect.collect(path, NOW, fetcher=lambda url: FIXTURE)
            self.assertEqual(len(again), 3)

    def test_old_articles_are_dropped(self):
        old = {"title": "古い記事", "url": "", "source": "x", "published": "2026-01-01T00:00:00+00:00"}
        self.assertEqual(collect.merge([old], [], NOW), [])

    def test_all_queries_failing_raises(self):
        def boom(url):
            raise OSError("down")
        with TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                collect.collect(Path(d) / "a.json", NOW, fetcher=boom)


class AnalyzeTest(unittest.TestCase):
    def test_classify_priority(self):
        self.assertEqual(analyze.classify("【マイルCS予想】本命はこの馬")[0], "yoso")
        self.assertEqual(analyze.classify("【マイルCS展望】注目の一戦")[0], "tenbo")
        self.assertEqual(analyze.classify("ラフターラインズが優勝")[0], "kekka")
        self.assertEqual(analyze.classify("競馬場でイベント開催")[0], "other")

    def test_find_races_aliases_and_order(self):
        races = analyze.find_races("【エ女杯】オークス馬は不発 次はマイルCSへ")
        self.assertEqual([n for n, _g in races], ["エリザベス女王杯", "マイルチャンピオンシップ"])

    def test_longest_race_name_wins(self):
        races = analyze.find_races("東京スポーツ杯2歳ステークスの展望")
        self.assertEqual(races, [("東京スポーツ杯2歳ステークス", "G2")])

    def test_find_jockeys(self):
        self.assertEqual(analyze.find_jockeys("アクアヴァーナル 松山弘平騎手と女性騎手"), ["松山弘平"])
        self.assertEqual(analyze.find_jockeys("ルメール騎手が1万回騎乗"), ["ルメール"])

    def test_summary_and_render(self):
        with TemporaryDirectory() as d:
            articles, _ = collect.collect(Path(d) / "a.json", NOW, fetcher=lambda url: FIXTURE)
        enriched = analyze.enrich(articles)
        s = analyze.summarize(enriched, NOW)
        mile = next(r for r in s["races"] if r["name"] == "マイルチャンピオンシップ")
        self.assertEqual(mile["status"], "upcoming")
        self.assertEqual(mile["count"], 2)
        self.assertIn("エンブロイダリー", mile["horses"])
        html = render.render(s, enriched)
        self.assertIn("<title>競馬ニュースウォッチ</title>", html)
        self.assertIn("マイルチャンピオンシップ", html)
        self.assertNotIn("</script><", html.split('id="data"')[1].split("</script>")[0])


if __name__ == "__main__":
    unittest.main()
