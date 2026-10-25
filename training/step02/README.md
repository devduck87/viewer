# Step 2: Layer の階層

Page の中の Layer を再帰的に読み込み、階層をコンソールに出力します。

## ゴール

```text
> py run.py ../../samples/basic
Page: Page 1

artboard: Home
  group: Header
    rectangle: Background  [unsupported]
    text: Title  [unsupported]
  group: Content
  ...
    rectangle: Hidden Badge  [hidden, unsupported]

未対応 Layer: bitmap x2, oval x2, rectangle x8, ...
```

- 字下げで親子関係を表す
- 非表示の Layer には `hidden`、まだ描画に対応していない種類には `unsupported` を付ける
- 不正な Layer データがあっても止まらず、`warning: ...` を出して読み込みを続ける

## 学ぶこと

- 再帰関数で木構造をたどる
- ジェネレーター (`yield` / `yield from`) で木構造を列挙する
- `dataclass` の `field(default_factory=list)`
- `collections.Counter` で件数を数える

## Layer の構造

Page JSON の `layers` に Layer が並び、Group などの Layer はさらに `layers` に子 Layer を持ちます。

```json
{
  "_class": "group",
  "do_objectID": "G-HEADER",
  "name": "Header",
  "isVisible": true,
  "frame": { "_class": "rect", "x": 20, "y": 20, "width": 360, "height": 60 },
  "layers": [
    { "_class": "rectangle", "name": "Background", "frame": { ... } },
    { "_class": "text", "name": "Title", "frame": { ... } }
  ]
}
```

| キー | 意味 |
|---|---|
| `_class` | Layer の種類 (`artboard` / `group` / `rectangle` / `text` など) |
| `do_objectID` | Layer の ID |
| `frame` | 位置とサイズ。**座標は親 Layer の左上を原点とした相対値** |
| `isVisible` | 表示するか |
| `layers` | 子 Layer。配列の先頭が最背面 |

## 変更するファイル

| ファイル | 内容 |
|---|---|
| `model.py` | `Frame` / `SketchLayer` を追加。`walk()`・`format_tree()`・`unsupported_layer_counts()` |
| `parser.py` | `_parse_layers()` / `_parse_layer()` で Layer を再帰的に解析。`ParseContext` で警告を集める |
| `run.py` | `format_tree()` の結果と警告・未対応 Layer の件数を出力する |

## 実装のポイント

### 再帰で読み、再帰でたどる

`_parse_layer()` は自分の `layers` を `_parse_layers()` に渡し、`_parse_layers()` は要素ごとに
`_parse_layer()` を呼びます。2 つの関数が互いを呼び合うことで、どれだけ深い階層でも読み込めます。

たどるときは `walk()` がジェネレーターとして `(layer, depth)` を順に返します。

```python
def walk(self, depth: int = 0) -> Iterator[tuple[SketchLayer, int]]:
    yield self, depth
    for child in self.children:
        yield from child.walk(depth + 1)
```

使う側は `for layer, depth in page.walk():` と書くだけで、再帰を意識せずに全 Layer を処理できます。

### 対応済みの種類を 1 か所にまとめる

`SUPPORTED_LAYER_TYPES` に、描画に対応した Layer の種類を書きます。
今は入れ物 (`group`) と画面 (`artboard` / `symbolMaster`) だけですが、回を追うごとに増やしていきます。
`unsupported` の数が減っていくのが進み具合の目安になります。

### 壊れたデータで止まらない

- `layers` が配列でない、配列の要素がオブジェクトでない → 警告を残して無視する
- 知らない `_class` → `SketchLayer` としてそのまま読み込む (子 Layer も読む)
- `frame` の値が数値でない → 0 として扱う (`_as_float()` は `bool` を数値として扱わない点に注意)

警告は `ParseContext.warnings` に集め、最後に `SketchDocument.warnings` として返します。

## 動作確認

```sh
py run.py ../../samples/basic
py run.py ../../samples/reference/symbols.sketch
```

## テスト

```sh
py -m unittest
```

`tests/test_model.py` (階層のたどり方・出力形式) と `tests/test_parser.py` (欠けた値・不正なデータ) が増えています。

## 発展課題

- `format_tree()` に「最大の深さ」を指定する引数を追加してみよう
- Layer の種類ごとの件数を一覧表示する `--stats` オプションを `run.py` に追加してみよう
