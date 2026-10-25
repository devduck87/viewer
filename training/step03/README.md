# Step 3: GUI の骨組み

Tkinter でウィンドウを作り、ファイルを開いて Layer の階層をツリー表示します。
描画はまだ行いません (右側の Canvas は Step 4 で使います)。

## ゴール

```sh
py run.py                              # 空のウィンドウを起動 -> File > Open... で開く
py run.py ../../samples/basic          # ファイルを開いた状態で起動
py run.py ../../samples/basic --dump   # Step 2 と同じコンソール出力
```

- File メニュー (Open... / Exit)、Ctrl+O でファイルを開く
- 左に Layer Tree (名前と種類)、右に灰色の Canvas、下にステータスバー
- 開けないファイルはエラーダイアログを表示する
- Tree の項目を選ぶと、ステータスバーに選択した項目を表示する

## 学ぶこと

- Tkinter の基本: `tk.Tk` / `ttk` ウィジェット / `pack` と `grid` / `PanedWindow`
- メニューとキーボードショートカット (`bind_all`)
- `ttk.Treeview` で木構造を表示する
- イベントとコールバック: 部品 (Layer Tree) から親 (App) へ、関数を渡して通知する
- `filedialog` / `messagebox`

## 追加するファイル

| ファイル | 内容 |
|---|---|
| `app.py` | `SketchViewerApp` (メインウィンドウ) と `main()` |
| `layer_tree.py` | `LayerTree`: Treeview を包んだ部品 |
| `run.py` | 引数なし / パス指定で GUI を起動。`--dump` で Step 2 と同じ出力 |

## 実装のポイント

### 画面の組み立てはメソッドに分ける

`__init__` に全部書くと長くなるので、`_build_menu()` / `_build_status_bar()` / `_build_panes()` のように
画面の部分ごとにメソッドを分けます。

`pack` は「呼んだ順に、指定した辺から場所を取る」ことに注意します。
ステータスバー (`side=BOTTOM`) を先に置いてから、残りの領域を `PanedWindow` (`fill=BOTH, expand=True`) で埋めます。

### 部品はコールバックで親に知らせる

`LayerTree` は「項目が選ばれた」ことを、コンストラクタで受け取った関数で App に知らせます。

```python
self.layer_tree = LayerTree(paned, on_select=self._on_tree_select)
```

`LayerTree` は App のことを知りません。部品どうしの依存を減らすと、部品を単独で理解・修正しやすくなります。
今後の回で Renderer やプロパティ欄が増えても、それらをつなぐのは App の役目です。

### Treeview の項目と Layer を対応づける

Treeview の項目は文字列の ID (item id) で管理されます。
`self._items[item_id] = (page, layer)` という辞書を作っておき、選択イベントで item id から Layer を引きます。
Page の項目は `layer` を `None` にします。

### GUI の起動はファイルを開いた後で

`run.py` からパスを渡された場合は、`root.after_idle(app.open_path, path)` で
ウィンドウが表示されてからファイルを開きます。

## 動作確認

- `py run.py ../../samples/basic` で Tree に 3 つの Page が表示される
- Tree の項目をクリックすると、ステータスバーに `選択: Page 1 / group: Header` のように表示される
- File > Open... で `samples/reference/*.sketch` を開ける
- 存在しない / 壊れたファイルを開くとエラーダイアログが出る

## テスト

```sh
py -m unittest
```

GUI はテストしにくいため、テストは Step 2 と同じです。
画面に関係しない処理を GUI から分けておくことが、Step 4 以降で効いてきます。

## 発展課題

- Tree に「子 Layer の数」を表示する列を追加してみよう
- File メニューに「最近開いたファイル」を追加してみよう (アプリ終了で消えてよい)
