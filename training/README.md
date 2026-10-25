# Sketch Viewer 研修カリキュラム

Sketch の `.sketch` ファイルを開いて、Page / Layer の階層と図形を表示するビューワーを、
全 8 回で少しずつ作ります。最終回 (Step 8) で、プロジェクト直下の Sketch Viewer と同じ機能になります。

- 使うもの: Python 3.10 以降の標準ライブラリのみ (`zipfile` / `json` / `dataclasses` / `tkinter` / `unittest`)
- 前提知識: Python の基本文法 (関数・クラス・例外・リスト / 辞書の内包表記)

## 各回の内容

| 回 | テーマ | できるようになること | 新しく作るファイル |
|---|---|---|---|
| [Step 1](step01/README.md) | ファイルを開く | `.sketch` (ZIP) を開き、Page の一覧を出力する | `errors.py` `reader.py` `model.py` `parser.py` |
| [Step 2](step02/README.md) | Layer の階層 | Layer を再帰的に読み込み、階層をコンソールへ出力する | (`model.py` `parser.py` を拡張) |
| [Step 3](step03/README.md) | GUI の骨組み | ウィンドウ・メニュー・Layer Tree を表示する | `app.py` `layer_tree.py` |
| [Step 4](step04/README.md) | 描画の基本 | 画面・矩形・楕円・文字を Canvas に描き、選択した Layer を強調する | `layout.py` `renderer.py` |
| [Step 5](step05/README.md) | 図形と座標変換 | パス・角丸・回転・反転を描き、Canvas のクリックで選択する | `geometry.py` |
| [Step 6](step06/README.md) | 画像と Symbol | 画像を表示し、Symbol Instance に Master の内容を展開する | `images.py` `symbols.py` |
| [Step 7](step07/README.md) | 表示の操作 | 拡大・縮小、表示する画面の切り替えを行う | `zoom.py` |
| [Step 8](step08/README.md) | 情報の確認 | プロパティ表示・表示 / 非表示の切り替え・検索を行う | `properties.py` |

Step 1-2 はコンソールアプリ、Step 3 以降は GUI アプリです。
各回のコードは単体で動き、前の回のコードに機能を追加した形になっています。

## 進め方

1. その回の `stepNN/README.md` で、ゴールと実装のポイントを確認する
2. 前の回のフォルダ (Step 1 は空のフォルダ) をコピーして作業用フォルダを作り、実装する
3. その回の `tests/` をコピーして実行し、すべて通ることを確認する
4. 動作確認のコマンドを実行して、結果を確かめる
5. `stepNN/` のコードと見比べて答え合わせをする

前の回との差分を見ると、その回で何を追加したかがわかります。

```sh
git diff --no-index training/step04 training/step05
```

## フォルダ構成

```text
training/
  README.md          このファイル
  step01/ ... step08/
    README.md        その回の説明
    run.py           エントリーポイント
    src/sketch_viewer/
    tests/
samples/             サンプルデータ (全ステップで共有)
  basic/             開発用の展開済みサンプル
  reference/         Sketch 公式のリファレンスファイル
```

`stepNN/` を別の場所へ移すとサンプルデータが見つからなくなるため、このフォルダ構成のまま使ってください
(テストは `training/stepNN/tests/` から 2 つ上のフォルダの `samples/` を参照します)。

## 実行方法

各ステップのフォルダへ移動してから実行します。

```sh
cd training/step08
py run.py ../../samples/basic            # GUI で開く (Step 3 以降)
py run.py ../../samples/basic --dump     # Layer 階層をコンソールへ出力 (Step 3 以降)
py -m unittest                           # テスト
```

Step 1-2 は GUI がないため、`py run.py ../../samples/basic` でコンソールへ出力します。

## 全体の設計

処理は次の順に流れます。各モジュールは自分より左のものだけを使います。

```text
Reader -> Parser -> Model -> Layout -> Renderer -> GUI
```

| モジュール | 役割 | 登場 |
|---|---|---|
| `errors.py` | 例外クラス (すべて `SketchError` の派生) | Step 1 |
| `reader.py` | ZIP / 展開済みフォルダから内部ファイルを読む | Step 1 |
| `model.py` | 内部モデル (`SketchDocument` / `SketchPage` / `SketchLayer` など) | Step 1 |
| `parser.py` | Sketch JSON を内部モデルへ変換する | Step 1 |
| `app.py` | メインウィンドウ。部品どうしをつなぐ | Step 3 |
| `layer_tree.py` | Layer Tree (ttk.Treeview) | Step 3 |
| `layout.py` | Layer の Page 上の位置を計算する (Tkinter 非依存) | Step 4 |
| `renderer.py` | Canvas に描画する | Step 4 |
| `geometry.py` | アフィン変換・曲線の折れ線近似・当たり判定 (Tkinter 非依存) | Step 5 |
| `images.py` | 画像データの取得 | Step 6 |
| `symbols.py` | Symbol Instance の展開 | Step 6 |
| `zoom.py` | 表示倍率の計算 (Tkinter 非依存) | Step 7 |
| `properties.py` | プロパティ欄 | Step 8 |

設計で大切にしていること:

- **GUI / Renderer は Sketch JSON を直接見ない。** JSON の読み取りは Parser に閉じ込め、それ以外は内部モデルだけを扱う
- **計算と画面表示を分ける。** 位置の計算 (`layout.py` `geometry.py` `zoom.py`) は Tkinter を使わないので、単体テストできる
- **壊れたデータで止まらない。** 未知の Layer や欠けた値は既定値で補い、警告を残して読み込みを続ける

## プロジェクト直下のコードとの対応

Step 8 は、プロジェクト直下の `src/sketch_viewer/` と同じ機能を、読みやすさを優先して分割し直したものです。

| プロジェクト直下 | Step 8 |
|---|---|
| `gui.py` | `app.py` (メインウィンドウ) / `layer_tree.py` / `properties.py` / `zoom.py` |
| `renderer.py` | `layout.py` (位置の計算) / `renderer.py` (描画) |
| `parser.py` | `parser.py` / `images.py` / `symbols.py` |
| その他 | ほぼ同じ |
