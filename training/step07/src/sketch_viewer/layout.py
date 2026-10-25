"""Layer の配置計算 (Tkinter 非依存)。

Sketch の Layer の frame は親 Layer からの相対座標で、回転・反転も親から子へ引き継がれる。
ここでは Layer ごとに「ローカル座標 -> Page 座標」の変換を求め、描画順に並べる。
Tkinter に依存しないため、単体テストで結果を確認できる。
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import Affine, Point, bounding_frame, layer_transform, rect_points
from .model import Frame, SketchLayer, SketchPage, Style, TextLayer


@dataclass(frozen=True)
class DrawItem:
    """描画する 1 つの Layer と、その Page 上での配置。"""

    layer: SketchLayer
    frame: Frame  # Page 座標での外接矩形 (回転後の形を囲む矩形)
    style: Style  # 描画に使うスタイル (shapeGroup の子の図形は親のスタイル)
    transform: Affine  # Layer のローカル座標 (frame の左上が原点) -> Page 座標

    def outline(self) -> list[Point]:
        """Layer の範囲 (回転・反転後) の 4 頂点を Page 座標で返す。"""
        return _outline(self.layer, self.transform)


def layout_page(page: SketchPage, roots: list[SketchLayer] | None = None) -> list[DrawItem]:
    """表示対象の Layer を描画順 (背面 -> 前面) に並べ、Page 上の配置を計算する。

    - layers 配列は先頭が最背面。親は子より先 (背面) に描く。
    - 非表示の Layer は子孫ごと除外する。
    - roots を指定すると、その Page 直下の Layer (画面) だけを対象とする。
    - shapeGroup の塗り・線は shapeGroup 自身に定義され、子の図形は形状だけを表す。
      そのため子の図形には shapeGroup のスタイルを割り当てる。
    """
    items: list[DrawItem] = []

    def visit(layer: SketchLayer, parent_transform: Affine, group_style: Style | None) -> None:
        if not layer.visible:
            return
        transform = parent_transform @ layer_transform(layer)
        frame = bounding_frame(_outline(layer, transform))
        items.append(DrawItem(layer, frame, _drawing_style(layer, group_style), transform))

        child_group_style = layer.style if layer.type == "shapeGroup" else None
        for child in layer.children:
            visit(child, transform, child_group_style)

    for top in page.layers:
        if roots is None or any(top is r for r in roots):
            visit(top, Affine(), None)
    return items


def bounds_of(items: list[DrawItem]) -> Frame | None:
    """描画対象全体を囲む矩形を返す。対象がなければ None。"""
    if not items:
        return None
    left = min(item.frame.x for item in items)
    top = min(item.frame.y for item in items)
    right = max(item.frame.right for item in items)
    bottom = max(item.frame.bottom for item in items)
    return Frame(left, top, right - left, bottom - top)


def _outline(layer: SketchLayer, transform: Affine) -> list[Point]:
    return [transform.apply(x, y) for x, y in rect_points(layer.frame.width, layer.frame.height)]


def _drawing_style(layer: SketchLayer, group_style: Style | None) -> Style:
    """描画に使うスタイル。shapeGroup の中の図形は shapeGroup のスタイルを使う。"""
    if group_style is not None and not isinstance(layer, TextLayer):
        return group_style
    return layer.style
