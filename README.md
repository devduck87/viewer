# Sketch Viewer

Sketch の `.sketch` ファイルを読み込み、Page / Layer 階層と基本図形を表示する閲覧専用ビューワーです。
Python 3.10 以降の標準ライブラリ (Tkinter) のみで動作します。

## 使い方

```sh
py run.py                          # GUI を起動 (File > Open... で .sketch を開く)
py run.py path/to/file.sketch      # ファイルを開いた状態で GUI を起動
py run.py samples/basic            # 展開済みディレクトリも開ける
py run.py samples/basic --dump     # GUI を使わず Layer 階層をコンソールへ出力
```

`--dump` の出力例:

```text
Page: Page 1

artboard: Home
  group: Header
    rectangle: Background
    text: Title
  ...
```

## テスト

```sh
py -m unittest
```

## 構成

```text
src/sketch_viewer/
  reader.py    ZIP / 展開済みディレクトリから内部ファイルを取得 (ZipSketchReader / DirectorySketchReader)
  parser.py    document.json -> pages/*.json -> Layer を再帰的に解析し内部モデルへ変換
  model.py     SketchDocument / SketchPage / SketchLayer / Frame、階層のテキスト出力
  geometry.py  アフィン変換 (回転・反転)、ベジェ曲線・角丸の折れ線近似 (Tkinter 非依存)
  renderer.py  内部モデルを Canvas へ描画 (座標計算 layout_page は Tkinter 非依存)
  gui.py       Tkinter GUI (File メニュー、Layer Tree、Canvas)
  errors.py    例外 (すべて SketchError の派生)
samples/basic/ 開発用の展開済みサンプル (Page 3 は回転・反転・角丸・パス・画像・Symbol の確認用)
```

処理の流れ: `Reader -> Parser -> Model -> Renderer -> Canvas`。
Renderer / GUI は Sketch JSON を直接参照しません。

## 対応状況

| Layer | 状態 |
|---|---|
| Group | 対応 (子 Layer の座標原点として使用) |
| Artboard / Symbol Master | 対応 (背景色と名前を表示) |
| Shape Group | 対応 (塗り・線を子の図形に適用) |
| Rectangle / Oval / Shape Path / Triangle / Star / Polygon | 対応 (塗り・線の色と太さ、ベジェ曲線、角丸、開いたパス) |
| Text | 対応 (文字列・フォント・サイズ・色・固定幅の折り返し・回転) |
| Bitmap | 対応 (PNG / GIF を frame の大きさに拡縮して表示、左右・上下反転) |
| Symbol Instance | 対応 (Master の内容を展開。ライブラリの Symbol、Override、入れ子 Symbol) |
| Slice | 対応 (書き出し範囲のため描画しない。Layer Tree で選択すると範囲を強調表示) |
| その他 (Hotspot など) | 未対応。枠線と名前のみ表示 |

- 非表示 Layer は描画しません (Layer Tree には `(hidden)` として表示)。
- Layer Tree で Layer を選択すると Canvas 上で範囲を強調表示します (回転後の形状に沿う)。
- 未知の Layer や不正な Layer データがあっても読み込みは継続します。
- 回転・反転は frame の中心を基準に子 Layer へも適用します。
- 曲線は折れ線で近似して描画します。boolean 演算 (合成・型抜き) は反映されません。
- 塗り・線は最前面の有効な単色のみ使用します (グラデーション等は無視)。
- Text の書式は先頭の文字属性のみ使用します (部分的な書式変更は反映されません)。Text の反転は反映されません。
- Tkinter Canvas は半透明を扱えないため、opacity・色の alpha は反映されません。
- 塗りも線もない図形は、位置確認用に薄い点線で表示します。
- Bitmap:
  - Tkinter の制約で JPEG などは表示できず、回転も反映されません (回転後の中心に配置)。
  - 拡縮は整数比の近似のため、frame とわずかに大きさが異なる場合があります。
  - 画像を読み込めない場合は枠線と理由を表示します。
- Symbol Instance:
  - Override は文字列 (`stringValue`)、入れ子 Symbol の差し替え (`symbolID`)、画像 (`image`) に対応します。
    スタイルの Override は反映されません。
  - Master と大きさが異なる instance は、子 Layer の frame を比例して伸縮します
    (resizing constraint・Smart Layout は考慮しません。文字サイズは変わりません)。
  - Master が見つからない場合は警告を出し、枠線と名前を表示します。

## テストデータ

`samples/reference/` に Sketch 公式の
[sketch-reference-files](https://github.com/sketch-hq/sketch-reference-files) (document version 123, MIT License) を同梱しています。

- `expanded/<name>/` : 公式リポジトリの展開済み JSON そのまま
- `<name>.sketch` : 上記を ZIP にまとめたもの

公式リポジトリには画像ファイルが含まれないため、`images` は画像なし (警告あり) として表示されます。

```sh
py run.py samples/reference/groups.sketch
```
