"""Layer の配置計算 (Tkinter 非依存)。

Sketch の Layer の frame は親 Layer からの相対座標になっている。
ここでは親の位置を足し合わせて Page 上の絶対座標を求め、描画順に並べる。
Tkinter に依存しないため、単体テストで結果を確認できる。
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Frame, SketchLayer, SketchPage


@dataclass(frozen=True)
class DrawItem:
    """描画する 1 つの Layer と、その Page 上での配置。"""

    layer: SketchLayer
    frame: Frame  # Page 座標での位置とサイズ


def layout_page(page: SketchPage) -> list[DrawItem]:
    """表示対象の Layer を描画順 (背面 -> 前面) に並べ、Page 上の位置を計算する。

    - layers 配列は先頭が最背面。親は子より先 (背面) に描く。
    - 非表示の Layer は子孫ごと除外する。
    """
    items: list[DrawItem] = []

    def visit(layer: SketchLayer, parent_x: float, parent_y: float) -> None:
        if not layer.visible:
            return
        frame = layer.frame.offset(parent_x, parent_y)
        items.append(DrawItem(layer, frame))
        for child in layer.children:
            visit(child, frame.x, frame.y)

    for top in page.layers:
        visit(top, 0.0, 0.0)
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
