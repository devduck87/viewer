# Step 4: 描画の基本

Layer の位置を計算して、画面 (Artboard)・矩形・楕円・文字を Canvas に描きます。

## ゴール

- Page を開くと、Canvas に Artboard (背景色と名前)、rectangle / oval (塗りと線)、text が表示される
- Tree で Page を選ぶとその Page を表示し、Layer を選ぶと赤い点線で範囲を強調する
- マウスホイールで縦、Shift + ホイールで横にスクロールできる
- まだ対応していない Layer は、点線の枠と名前だけを表示する

## 学ぶこと

- 相対座標から絶対座標への変換
- 「計算」と「描画」を分ける設計 (Tkinter を使わない部分は単体テストできる)
- `tk.Canvas` の図形 (`create_rectangle` / `create_oval` / `create_text`) とタグ
- スクロール領域 (`scrollregion`)

## 追加・変更するファイル

| ファイル | 内容 |
|---|---|
| `model.py` | `Color` / `Border` / `Style` / `TextLayer` を追加。`SketchLayer.style` |
| `parser.py` | `parse_style()` (塗り・線)、`_parse_text()` (文字列・フォント)、Artboard の背景色 |
| `layout.py` (新規) | `layout_page()`: Layer を描画順に並べ、Page 上の位置を計算する |
| `renderer.py` (新規) | `CanvasRenderer`: Canvas への描画と強調表示 |
| `app.py` | Page の表示 (`_show_page()`)、選択時の強調、ホイールでのスクロール |

## Sketch のスタイルと文字

```json
"style": {
  "fills":   [ { "isEnabled": true, "fillType": 0, "color": { "red": 1, "green": 0, "blue": 0, "alpha": 1 } } ],
  "borders": [ { "isEnabled": true, "fillType": 0, "thickness": 2, "color": { ... } } ],
  "contextSettings": { "opacity": 1 }
}
```

- `fills` / `borders` は**配列の末尾が最前面**。有効 (`isEnabled`) な単色 (`fillType: 0`) のうち最前面のものを使う
- 色の各成分は 0.0 - 1.0。Tkinter の `#rrggbb` に変換する
- Artboard の背景色は `style` ではなく `backgroundColor` にある (`hasBackgroundColor` が true のときだけ使う)
- Text の文字列は `attributedString.string`、フォントや色は `attributedString.attributes[0].attributes` にある

## 実装のポイント

### 位置の計算は layout.py に分ける

Layer の `frame` は親からの相対座標なので、親の位置を足しながら木をたどります。

```text
Home (0, 0) > Content (20, 100) > Footer (0, 170) > Button (240, 0)
=> Button の Page 上の位置は (260, 270)
```

`layout_page()` は Tkinter を使わずに `DrawItem(layer, frame)` のリストを返すだけなので、
`tests/test_layout.py` で計算結果を確かめられます。並び順がそのまま描画順 (背面 -> 前面) です。

### Renderer は描くことに専念する

`CanvasRenderer.render(page)` は次の順に処理します。

1. `layout_page()` で配置を求める
2. 全体を囲む矩形 (`bounds_of()`) を求め、左上に余白 (margin) ができるよう平行移動する
3. Layer の種類ごとのメソッド (`_draw_artboard()` / `_draw_shape()` / `_draw_text()` ...) で描く
4. `scrollregion` を設定して、描いた範囲をスクロールできるようにする

強調表示の図形には `tags="highlight"` を付けておき、`canvas.delete("highlight")` でまとめて消します。

### Tkinter の制約

- Canvas は半透明を描けないため、色の alpha は無視する (alpha = 0 のときだけ描かない)
- フォント名は PostScript 名 (`Arial-BoldMT`) で入っているため、`tk_font()` で `("Arial", -28, "bold")` に変換する。
  サイズを負の値にするとピクセル単位になる

## 動作確認

- `py run.py ../../samples/basic` の Page 1 で、Home 画面のボタンやカードが表示される
- Tree で `Button` を選ぶと、Canvas 上のボタンが赤い点線で囲まれる
- Page 3 は、回転・角丸がまだ反映されず、星やパスは点線の枠 (未対応) で表示される

## テスト

```sh
py -m unittest
```

`tests/test_layout.py` (位置の計算) と `tests/test_renderer.py` (フォント名の変換) が増えています。

## 発展課題

- Artboard の名前の文字サイズや色を定数にまとめ、変えてみよう
- 線の太さを 0.5 刻みで扱えるか確かめてみよう (Tkinter の `width` に小数を渡すとどうなるか)
