# Step 8: 情報の確認

選択した Layer のプロパティ表示、表示 / 非表示の切り替え、検索を追加して完成です。
プロジェクト直下の Sketch Viewer と同じ機能になります。

## ゴール

- **プロパティ欄** (左下): 名前・種類・所属する画面・位置・サイズ・回転・塗り / 線 / 文字の色 (色見本付き)・フォント。値はコピーできる
  - 座標は、Layer が所属する画面の左上を原点とする (画面に属さない Layer は Page 座標)
  - 回転した Layer は回転前の矩形 (中心は回転後と同じ) の位置とサイズを表示する (Sketch の Inspector と同じ)
- **表示 / 非表示**: Layer Tree のチェックボックス (または Space キー) で切り替える
  - チェックを外した Layer は子孫ごと描画しない。子孫は灰色になり、子孫のチェック状態は保持する
  - Sketch 上で非表示の Layer は、チェックが外れた状態で開く
  - 表示を切り替えても描画位置がずれない
- **検索** (Ctrl+F): 名前または Text の文字列に一致する Layer とその親だけに Tree を絞り込む
  - Enter / Shift+Enter で次 / 前の一致を選択、Esc で解除。一致件数を表示する

## 学ぶこと

- 表示用の値を作る処理と、ウィジェットに表示する処理を分ける
- 状態 (チェックの有無) を持つ部品の設計
- `after` / `after_cancel` による入力の間引き (デバウンス)
- ポリモーフィズム (`TextLayer.matches()` のオーバーライド)

## 追加・変更するファイル

| ファイル | 内容 |
|---|---|
| `properties.py` (新規) | `describe_layer()` (表示する文字列を作る) と `PropertiesPanel` |
| `layout.py` | `layout_page(page, is_visible, roots)`、`show_all()`、`Placement` / `placement_of()`、`DrawItem.root` |
| `renderer.py` | `render(..., is_visible, ...)`。描画範囲は非表示の Layer も含めて求める |
| `model.py` | `SketchLayer.matches()` / `TextLayer.matches()` |
| `layer_tree.py` | チェックボックス、検索での絞り込み、一致の移動 |
| `app.py` | 検索欄・プロパティ欄の配置と、部品どうしの連携 |

## 実装のポイント

### 表示する値の計算はウィジェットから分ける

`describe_layer(page, layer)` は「キー -> 表示する文字列」の辞書と、色見本の色を返すだけの関数です。
`PropertiesPanel.show()` はその結果をウィジェットに入れるだけにします。
こうすると、表示内容を `tests/test_properties.py` で確かめられます。

位置は `placement_of()` で求めます。Layer の変換で frame の中心を Page 座標に写し、
そこに回転前の大きさの矩形を置き、所属する画面の左上を引きます。

### 表示 / 非表示の状態は Layer Tree が持つ

チェックを外した Layer は `id(layer)` の集合 (`_hidden`) で管理し、モデル (`layer.visible`) は書き換えません。
Renderer には `layer_tree.is_visible` という関数を渡し、`layout_page()` がその関数で描画対象を絞り込みます。

描画範囲を描画対象だけで求めると、Layer を隠したときに全体の位置がずれてしまいます。
そこで描画範囲は `show_all` (すべて表示) で配置した結果から求め、実際に描くのは `is_visible` で絞り込んだ結果にします。

### 検索は入力が止まってから行う

1 文字入力するたびに Tree を作り直すと重くなるため、入力のたびに `after(200, ...)` で予約し直し、
200 ms 入力がなかったときだけ絞り込みます (デバウンス)。
Tree を作り直すときは、一致した Layer、または一致する子孫を持つ Layer だけを残します。

### 検索で隠れた Layer をクリックしたとき

Canvas のクリックで選んだ Layer が検索で Tree から外れている場合は、Tree の選択を外したうえで、
その Layer を強調し、プロパティを表示します。

## 動作確認

- `py run.py ../../samples/basic` で `Button` を選ぶと、プロパティ欄に `X 260 / Y 270 / W 120 / H 30` と緑の色見本が出る
- Page 3 の `Rotated 30` は回転 `30°`、位置は回転前の矩形で表示される
- `Content` のチェックを外すと、中身ごと消え、子孫が灰色になる。他の図形の位置は動かない
- 検索欄に `label` と入力すると、`Label` を含む Layer とその親だけが残る。Enter で順に選択される

## テスト

```sh
py -m unittest
```

`tests/test_properties.py` と、`tests/test_layout.py` に表示の絞り込み・位置 (`placement_of()`) のテストが加わっています。

## 発展課題

- 検索で大文字・小文字を区別するチェックボックスを追加してみよう
- プロパティ欄に、Symbol Instance の参照先の Master 名を表示してみよう
- 表示 / 非表示の状態をファイルごとに保存し、次に開いたときに復元してみよう
