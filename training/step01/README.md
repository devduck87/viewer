# Step 1: ファイルを開く

`.sketch` ファイルを開き、含まれている Page の名前を一覧表示するコンソールアプリを作ります。

## ゴール

```text
> py run.py ../../samples/basic
Page: Page 1
Page: Page 2
Page: Page 3
```

存在しないファイルや壊れたファイルを指定したときは、`error: ...` を表示して終了コード 1 で終わること。

## 学ぶこと

- `zipfile` で ZIP の中のファイルを読む、`json` でパースする
- `abc.ABC` による抽象基底クラス (読み込み元が ZIP でもフォルダでも同じように扱う)
- 独自の例外クラスの階層
- `dataclasses.dataclass` によるデータの入れ物
- `with` 文で使えるクラス (`__enter__` / `__exit__`)
- `unittest` によるテスト

## Sketch ファイルの構造

`.sketch` ファイルの正体は ZIP です。中には次のファイルが入っています。

```text
document.json          文書全体の情報。Page ファイルへの参照を持つ
meta.json              作成したアプリのバージョンなど
user.json              ユーザーごとの表示設定
pages/<ID>.json        Page ごとの内容 (Layer の階層)
images/<ID>.png        画像
```

`document.json` の `pages` は Page ファイルへの参照の配列です。拡張子 `.json` は省略されています。

```json
{
  "do_objectID": "DOC-0001",
  "pages": [
    { "_class": "MSJSONFileReference", "_ref": "pages/PAGE-0001" }
  ]
}
```

`samples/basic/` は ZIP を展開した状態のサンプルです。開発中は中身を直接見られるフォルダが便利なので、
**ZIP とフォルダのどちらからでも読める**ようにします。

## 作るファイル

| ファイル | 内容 |
|---|---|
| `errors.py` | 例外クラス。すべて `SketchError` を継承する |
| `reader.py` | `SketchReader` (抽象クラス) と `ZipSketchReader` / `DirectorySketchReader`、`open_reader()` |
| `model.py` | `SketchDocument` / `SketchPage` |
| `parser.py` | `load_document()`: document.json -> 各 Page JSON を読み、`SketchDocument` を返す |
| `run.py` | コマンドライン引数を受け取り、Page 名を出力する |

## 実装のポイント

### 例外は階層にする

```text
SketchError
  SketchFileNotFoundError   ファイルがない
  InvalidSketchFileError    ZIP として開けない
  MissingEntryError         document.json などがない
    PageNotFoundError       参照先の Page JSON がない
  InvalidJSONError          JSON として不正
  SketchFormatError         JSON は読めたが期待した構造ではない
```

呼び出し側 (`run.py`) は `SketchError` を 1 つ捕まえるだけで、すべての読み込みエラーを処理できます。
標準の例外 (`zipfile.BadZipFile` / `json.JSONDecodeError` など) は Reader の中で捕まえ、
`raise ... from exc` で独自の例外に変換します。

### Reader で読み込み元の違いを隠す

```python
class SketchReader(ABC):
    @abstractmethod
    def exists(self, name: str) -> bool: ...
    @abstractmethod
    def read_bytes(self, name: str) -> bytes: ...
    def read_json(self, name: str) -> Any: ...   # read_bytes を使って共通実装
```

Parser は `SketchReader` のメソッドだけを使い、ZIP かフォルダかを気にしません。
`DirectorySketchReader` では `"../document.json"` のようにフォルダの外を指すパスを読めないようにします
(`Path.is_relative_to()`)。

### JSON の値は型を確かめてから使う

JSON の値は欠けていたり、想定と違う型だったりすることがあります。
`data["name"]` と書くと、キーがないときに `KeyError` で止まってしまいます。
`_as_str(data.get("name"))` のように、型が違えば既定値にする小さな関数を用意します。

## 動作確認

```sh
py run.py ../../samples/basic
py run.py ../../samples/reference/groups.sketch    # ZIP 形式
py run.py nothing.sketch                           # error: ... (終了コード 1)
```

## テスト

```sh
py -m unittest
```

`tests/test_reader.py` は ZIP とフォルダで同じ結果になること、エラー時に正しい例外が出ることを確認します。

## 発展課題

- `meta.json` の `appVersion` (Sketch のバージョン) も出力してみよう
- Page に含まれる Layer の数 (`layers` 配列の長さ) を Page 名の横に表示してみよう
