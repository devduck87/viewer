# Step 6: 画像と Symbol

画像 (Bitmap) を表示し、Symbol Instance に Symbol Master の内容を展開します。
これで、Sketch の主な Layer の種類をすべて描画できるようになります。

## ゴール

- Bitmap を frame の大きさに拡縮して表示する (左右・上下の反転にも対応)
- 画像がない・表示できない形式のときは、枠と理由を表示する
- Symbol Instance に Master の中身を表示する
  - 文字列・画像・入れ子 Symbol の差し替え (Override) を反映する
  - Master と大きさが違う instance は、子 Layer を比例して伸縮する
  - ライブラリから取り込んだ Symbol (`foreignSymbols`) も使う
- Slice (書き出し範囲) は描画しない
- `--dump` で「未対応 Layer」が表示されなくなる

## 学ぶこと

- Base64 と `tk.PhotoImage`、整数比での拡大・縮小 (`fractions.Fraction`)
- 「全部読み終えてから解決する」2 段階の処理
- `copy.deepcopy` による木構造の複製
- 循環参照の検出

## 追加・変更するファイル

| ファイル | 内容 |
|---|---|
| `images.py` (新規) | `load_image()`: 参照 (`images/xxx.png`) または埋め込みデータから画像を取得 |
| `symbols.py` (新規) | `SymbolResolver`: Master と Instance を集め、最後に展開する |
| `model.py` | `BitmapLayer` / `SymbolInstanceLayer` |
| `reader.py` | `read_image()` |
| `parser.py` | Bitmap / Symbol Instance の解析、`foreignSymbols`、最後に `expand_all()` |
| `renderer.py` | `_draw_bitmap()` / `_draw_symbol_instance()`、Slice は描かない |

## Sketch の画像と Symbol

```json
{ "_class": "bitmap", "image": { "_class": "MSJSONFileReference", "_ref": "images/photo.png" } }

{ "_class": "symbolMaster",   "symbolID": "SYM-BADGE", "layers": [ ... ] }
{ "_class": "symbolInstance", "symbolID": "SYM-BADGE",
  "overrideValues": [ { "overrideName": "T-LABEL_stringValue", "value": "NEW" } ] }
```

- 画像は `images/` 以下のファイルを参照する (拡張子が省略されていることもある)。JSON に Base64 で埋め込まれている場合もある
- Symbol Instance は子 Layer を持たず、`symbolID` で Master を参照するだけ
- Override の名前は `<Layer ID のパス>_<プロパティ名>`。入れ子の instance の中は `N1/T-LABEL_stringValue` のように `/` でつなぐ
- `symbolID` の Override が空文字のときは「なし」に差し替えられた (= 非表示) という意味

## 実装のポイント

### Symbol は最後にまとめて展開する

Instance が Master より前の Page にあることもあるため、読み込みながらは展開できません。
Parser は Layer を読むたびに `SymbolResolver` に Master / Instance を登録しておき、
すべての Page を読み終えてから `expand_all()` で展開します。

展開では Master の子 Layer を `copy.deepcopy` で複製します。
複製しないと、同じ Master を使う instance どうしで Layer を共有してしまい、Override が混ざります。

### 入れ子と循環参照

Master の中に別の Symbol Instance がある場合は、その instance も展開します (再帰)。
展開中の `symbolID` を `stack` に積んでおき、同じ ID が再び現れたら循環参照として警告を出して止めます。
外側の instance から渡された Override は、内側の instance 自身の Override より優先します。

### PhotoImage は整数倍でしか拡縮できない

`PhotoImage.zoom(n)` は n 倍に拡大、`subsample(n)` は 1/n に間引くことしかできません。
そこで目標の倍率を分数で近似し (`image_scale_factors()`)、`zoom(分子)` -> `subsample(分母)` の順に適用します。
また、作った `PhotoImage` は**参照を持ち続けないとガベージコレクションで消えて表示されなくなる**ため、
Renderer のリスト (`_photos`) に保持します。

## 動作確認

- `py run.py ../../samples/basic` の Page 2 に写真、Page 3 に反転した写真と Badge の instance が表示される
- `py run.py ../../samples/basic --dump` の最後に「未対応 Layer」が出ない
- `py run.py ../../samples/reference/symbol-overrides.sketch` で instance の文字列が `Custom label` になっている
- `py run.py ../../samples/reference/images.sketch` は画像ファイルがないため、枠と「画像なし」が表示される

## テスト

```sh
py -m unittest
```

`tests/test_parser.py` に Bitmap と Symbol (Override・入れ子・循環参照など) のテストが加わっています。

## 発展課題

- Symbol Instance を選んだとき、ステータスバーに参照先の Master 名を表示してみよう
- 同じ画像を何度も読み込まないよう、`load_image()` の結果をキャッシュしてみよう
