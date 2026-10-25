# Step 5: 図形と座標変換

パス (曲線・角丸) で図形を描き、回転・反転に対応します。Canvas のクリックで Layer を選択できるようにします。

## ゴール

- shapePath / star / triangle / polygon、角丸の rectangle、曲線を描ける
- 回転・反転した Layer (と、その子 Layer) を正しい向きで描ける
- Shape Group (`shapeGroup`) の塗り・線を子の図形に適用する
- Canvas 上の図形をクリックすると、その Layer が Tree で選択される
- 強調表示の点線が、回転後の形に沿う

## 学ぶこと

- アフィン変換 (平行移動・回転・拡大縮小・反転を行列 1 つで表す)
- 3 次ベジェ曲線と折れ線による近似
- 点が多角形の内側にあるかの判定 (交差数判定法)

## 追加・変更するファイル

| ファイル | 内容 |
|---|---|
| `geometry.py` (新規) | `Affine` / `layer_transform()` / `flatten_path()` / `contains_point()` など |
| `model.py` | `CurvePoint` / `ShapeLayer`、`rotation` / `flipped_horizontal` / `flipped_vertical` |
| `parser.py` | `_parse_shape()` (頂点列)、`parse_point()`、回転・反転 |
| `layout.py` | オフセットの足し算をアフィン変換に置き換える。`DrawItem` に `style` / `transform` を追加 |
| `renderer.py` | 図形を折れ線の多角形で描く。`layer_at()` (クリック判定)、回転後の範囲で強調 |
| `app.py` / `layer_tree.py` | Canvas のクリックで Tree の項目を選択する |

## Sketch の図形と回転

図形は `points` (頂点の配列) で表されます。座標は frame に対する**正規化値 (0.0 - 1.0)** の文字列です。

```json
"points": [
  { "point": "{0, 0}", "curveFrom": "{0, 0}", "curveTo": "{0, 0}",
    "hasCurveFrom": false, "hasCurveTo": false, "cornerRadius": 8 },
  ...
],
"isClosed": true
```

- `curveFrom` (次の頂点へ向かう制御点) / `curveTo` (前の頂点から来る制御点) で 3 次ベジェ曲線を表す
- `hasCurveFrom` / `hasCurveTo` が false なら、制御点は頂点と同じ位置 (= 直線)
- `rotation` は**frame の中心を基準に反時計回り**の角度 (度)。`isFlippedHorizontal` / `isFlippedVertical` で反転
- 回転・反転は子 Layer にも引き継がれる
- `shapeGroup` の場合、塗り・線は `shapeGroup` 自身にあり、子の図形は形だけを表す

## 実装のポイント

### なぜアフィン変換を使うのか

Step 4 では親の位置を足すだけで済みましたが、回転が入ると「親が 30 度回転していると、子の位置も回る」ため、
足し算では表せなくなります。そこで「Layer のローカル座標 -> 親の座標」を `Affine` で表し、
`親の変換 @ 自分の変換` のように掛け合わせて Page 座標への変換を作ります。

```python
# 中心を原点へ移す -> 反転 -> 回転 -> 中心を元に戻す -> frame の位置へ移す (右から順に適用)
transform = (Affine.translation(frame.x, frame.y) @ Affine.translation(cx, cy)
             @ Affine.rotation(-layer.rotation) @ Affine.scaling(flip_x, flip_y)
             @ Affine.translation(-cx, -cy))
```

Canvas 座標への変換 (余白分の平行移動) も同じ `Affine` で表せるため、
`to_canvas @ item.transform` 1 つで「Layer のローカル座標 -> Canvas 座標」が求まります。

### 曲線は折れ線で近似する

Tkinter の Canvas は回転した楕円やベジェ曲線を描けません。
`flatten_path()` で曲線を細かい直線 (1 区間 16 分割) に分け、`create_polygon()` で描きます。
角丸は、角の両側の辺上に接点を求め、その間を円弧に近い曲線で結びます (半径は辺の半分までに制限)。

### クリックした Layer を探す

Renderer は描いた Layer の範囲 (回転後の 4 頂点) を前面から順に持っておき、
クリック位置を含む最初の Layer を返します (`contains_point()`)。Group などの入れ物は対象外です。
App は `LayerTree.select_layer()` で Tree の項目を選ぶだけで、その後の処理は通常の選択と同じ流れになります。

## 動作確認

- `py run.py ../../samples/basic` の Page 3 で、角丸・回転・反転・星・波線が表示される
- 回転した図形を Tree で選ぶと、強調表示の点線も回転している
- Canvas 上の図形をクリックすると Tree の項目が選ばれる
- `py run.py ../../samples/reference/groups.sketch` で、Shape Group の緑の矩形が表示される

## テスト

```sh
py -m unittest
```

`tests/test_geometry.py` (変換・曲線・当たり判定) が増え、`tests/test_layout.py` に回転と Shape Group の確認が加わっています。

## 発展課題

- `CURVE_STEPS` を 4 や 64 に変えて、見た目と描画速度の違いを確かめてみよう
- `Affine` に逆変換 (`inverse()`) を追加し、Canvas 上のクリック位置を Layer のローカル座標に戻してみよう
