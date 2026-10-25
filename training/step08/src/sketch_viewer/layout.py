"""Layer の配置計算 (Tkinter 非依存)。

Sketch の Layer の frame は親 Layer からの相対座標で、回転・反転も親から子へ引き継がれる。
ここでは Layer ごとに「ローカル座標 -> Page 座標」の変換を求め、描画順に並べる。
Tkinter に依存しないため、単体テストで結果を確認できる。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .geometry import Affine, Point, bounding_frame, layer_transform, rect_points
from .model import Frame, SketchLayer, SketchPage, Style, TextLayer

# Layer を表示するかを判定する関数
VisibilityFilter = Callable[[SketchLayer], bool]


@dataclass(frozen=True)
class DrawItem:
    """描画する 1 つの Layer と、その Page 上での配置。"""

    layer: SketchLayer
    frame: Frame  # Page 座標での外接矩形 (回転後の形を囲む矩形)
    style: Style  # 描画に使うスタイル (shapeGroup の子の図形は親のスタイル)
    transform: Affine  # Layer のローカル座標 (frame の左上が原点) -> Page 座標
    root: SketchLayer  # Page 直下の祖先 Layer (自身が Page 直下なら自身)

    def outline(self) -> list[Point]:
        """Layer の範囲 (回転・反転後) の 4 頂点を Page 座標で返す。"""
        return _outline(self.layer, self.transform)


def show_all(_layer: SketchLayer) -> bool:
    """layout_page に渡すと、非表示の Layer も含めて配置する。"""
    return True


def visible_in_sketch(layer: SketchLayer) -> bool:
    """Sketch 上の表示設定に従う (layout_page の既定値)。"""
    return layer.visible


def layout_page(page: SketchPage, is_visible: VisibilityFilter = visible_in_sketch,
                roots: list[SketchLayer] | None = None) -> list[DrawItem]:
    """表示対象の Layer を描画順 (背面 -> 前面) に並べ、Page 上の配置を計算する。

    - layers 配列は先頭が最背面。親は子より先 (背面) に描く。
    - is_visible が False を返す Layer は子孫ごと除外する。
    - roots を指定すると、その Page 直下の Layer (画面) だけを対象とする。
    - shapeGroup の塗り・線は shapeGroup 自身に定義され、子の図形は形状だけを表す。
      そのため子の図形には shapeGroup のスタイルを割り当てる。
    """
    items: list[DrawItem] = []

    def visit(layer: SketchLayer, parent_transform: Affine, group_style: Style | None,
              root: SketchLayer) -> None:
        if not is_visible(layer):
            return
        transform = parent_transform @ layer_transform(layer)
        frame = bounding_frame(_outline(layer, transform))
        items.append(DrawItem(layer, frame, _drawing_style(layer, group_style), transform, root))

        child_group_style = layer.style if layer.type == "shapeGroup" else None
        for child in layer.children:
            visit(child, transform, child_group_style, root)

    for top in page.layers:
        if roots is None or any(top is r for r in roots):
            visit(top, Affine(), None, top)
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


@dataclass(frozen=True)
class Placement:
    """Layer の画面 (Artboard) 上での位置と描画スタイル。プロパティ欄の表示に使う。"""

    artboard: SketchLayer | None  # 所属する画面。画面の外にある Layer は None
    # 画面の左上を原点とした位置とサイズ (画面の外にある Layer は Page 座標)。
    # 回転・反転を戻した矩形で、中心は回転後の中心と一致する (Sketch の Inspector と同じ)
    frame: Frame
    rotation: float  # 画面上の回転角 (度、反時計回り。親の回転を含む)
    style: Style


def placement_of(page: SketchPage, layer: SketchLayer) -> Placement | None:
    """Layer の所属する画面と、画面を基準とした位置を求める。Page 内になければ None。

    非表示の Layer も対象とする。
    """
    items = layout_page(page, show_all)
    item = next((i for i in items if i.layer is layer), None)
    if item is None:
        return None

    # 回転前の大きさの矩形を、回転後の中心に置く
    width, height = layer.frame.width, layer.frame.height
    cx, cy = item.transform.apply(width / 2, height / 2)
    frame = Frame(cx - width / 2, cy - height / 2, width, height)

    artboard = item.root if item.root.is_artboard else None
    if artboard is not None:
        origin = next(i.frame for i in items if i.layer is artboard)
        frame = frame.offset(-origin.x, -origin.y)
    return Placement(artboard, frame, item.transform.angle, item.style)


def _outline(layer: SketchLayer, transform: Affine) -> list[Point]:
    return [transform.apply(x, y) for x, y in rect_points(layer.frame.width, layer.frame.height)]


def _drawing_style(layer: SketchLayer, group_style: Style | None) -> Style:
    """描画に使うスタイル。shapeGroup の中の図形は shapeGroup のスタイルを使う。"""
    if group_style is not None and not isinstance(layer, TextLayer):
        return group_style
    return layer.style
