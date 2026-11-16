# testplay

## 競馬ニュースウォッチ

JRA（中央競馬）のニュースを Google ニュースから集めます。見出しを分類・集計して、1 枚の Web ページにまとめます。

- **収集**: `keiba_news/config.py` の検索クエリで Google ニュースの RSS を取得します。重複をまとめて `data/articles.json` に 30 日分を保存します。
- **分類**: 見出しのキーワードで「予想・データ」「出走・展望」「レース結果」「騎手・調教師」「引退・移籍・繁殖」に分けます。
- **分析**: 見出しから重賞名（`keiba_news/races.py` の辞書）、騎手、調教師、馬名の候補を拾い、話題量を集計します。
- **出力**: `docs/index.html`。ブラウザで直接開けて、claude.ai の Artifact としても公開できます。

### 使い方

外部パッケージは不要で、Python 3.10 以上で動きます。

```bash
python -m keiba_news             # 収集してページを作る
python -m keiba_news --no-fetch  # 保存済みデータからページだけ作り直す
python -m keiba_news --days 3    # 集計期間を変える
python -m unittest discover -s tests
```

### 自動実行

`.github/workflows/keiba-news.yml` が毎日 6:17 と 18:17（日本時間）に収集し、`data/` と `docs/` の更新をコミットします。Actions タブの「Run workflow」から手動でも実行できます。

### カスタマイズ

- 調べたい話題を増やす: `config.py` の `QUERIES` に検索語を追加します。
- 分類の精度を上げる: `CATEGORIES` のキーワードと、`HORSE_STOPWORDS`（馬名ではないカタカナ語）を調整します。
- 重賞の追加やグレード変更: `races.py` の `GRADED_RACES` を編集します。

### 注意

- 見出しだけを機械的に処理しているため、誤分類や馬名の拾い漏れがあります。
- Google ニュースの RSS は個人的・非商用の利用に限られています。
