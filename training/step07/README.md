# Step 7: 表示の操作

拡大・縮小と、表示する画面 (Artboard) の切り替えを追加します。

## ゴール

- 上部のツールバーに「表示」(画面の選択) と「倍率」(− / 一覧 / + / 100% / 全体を表示)
- View メニューとショートカット: Ctrl++ / Ctrl+- / Ctrl+0 (100%) / Ctrl+9 (全体を表示)
- Ctrl + マウスホイールで、**カーソル位置を中心に**拡大・縮小する
- 中ボタンのドラッグで表示位置を動かす
- Layer Tree で画面をダブルクリックすると、その画面だけを表示する
- 選択した Layer が表示範囲の外にあれば、中央に来るようスクロールする
- 1 画面だけを表示しているときに別の画面の Layer を選ぶと、その画面に切り替える

## 学ぶこと

- 倍率の変更を座標変換に組み込む
- 倍率変更の前後で「カーソルの下の点」を動かさない計算
- `ttk.Combobox` / ツールバーの組み立て

## 追加・変更するファイル

| ファイル | 内容 |
|---|---|
| `zoom.py` (新規) | `ZOOM_LEVELS` / `next_zoom_level()` / `fit_zoom()` / `format_zoom()` (Tkinter 非依存) |
| `model.py` | `SketchPage.artboards()`: Page 直下の画面の一覧 |
| `layout.py` | `layout_page(page, roots)`: 指定した画面だけを配置する |
| `renderer.py` | `render(page, roots, scale)`: 倍率を Canvas 座標への変換に入れる |
| `app.py` | ツールバー・View メニュー・ショートカット、画面の切り替え、選択した Layer へのスクロール |
| `layer_tree.py` | ダブルクリックを `on_activate` で通知する |

## 実装のポイント

### 倍率は変換を 1 つ足すだけ

Step 5 で Canvas 座標への変換をアフィン変換にしてあるので、倍率は拡大縮小を 1 つ挟むだけで済みます。

```python
to_canvas = (Affine.translation(margin, margin)
             @ Affine.scaling(scale, scale)
             @ Affine.translation(-bounds.x, -bounds.y))
```

ただし、変換では表せないものは個別に倍率を掛ける必要があります。

- 線の太さ (`style.border.thickness * scale`)
- 文字の大きさと折り返し幅 (`font_size * scale`)
- 画像の大きさ (`frame.width * scale`)

前の回のコードで `self.scale` が必要になる場所を探してみましょう。

### カーソル位置を中心に拡大する

倍率を `r` 倍にすると、Canvas 上の点は余白 (margin) を基準に `r` 倍の位置へ移ります。

```text
新しい位置 = margin + (今の位置 - margin) * r
```

描き直した後、その点が再びカーソルの下に来るようにスクロール位置を合わせます
(`xview_moveto((新しい位置 - カーソルの位置) / 全体の幅)`)。

### 画面の切り替え

「表示」の選択肢は `[None, 画面1, 画面2, ...]` のリスト (`_view_choices`) と対応させ、None を「全体」とします。
1 画面だけを表示するときは、`layout_page(page, roots=[画面])` でその画面と子孫だけを配置します。
描画範囲もその画面の大きさになるため、スクロール領域も自然に小さくなります。

Layer がどの画面に属するかは、ファイルを開いたときに `id(layer) -> Page 直下の祖先` の辞書 (`_root_of`) を作っておきます。

## 動作確認

- `py run.py ../../samples/basic` で Ctrl + ホイールを回すと、カーソルの下の図形が動かずに拡大・縮小される
- 「全体を表示」でウィンドウに収まる倍率になる
- 「表示」で `Home` を選ぶと Home 画面だけが表示される。Tree で別画面の Layer を選ぶと画面が切り替わる
- Tree で Page 3 の `Badge` (種類が symbolMaster のもの) をダブルクリックすると、Badge だけが表示される

## テスト

```sh
py -m unittest
```

`tests/test_zoom.py` (倍率の計算) と、`tests/test_layout.py` に画面の絞り込みのテストが加わっています。

## 発展課題

- 倍率をステータスバーにも表示してみよう
- `ZOOM_LEVELS` に 12 や 16 を足したとき、画像の表示で困ることがないか確かめてみよう (`MAX_ZOOM_SIZE`)
