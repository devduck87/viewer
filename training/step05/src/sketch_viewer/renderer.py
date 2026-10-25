"""内部モデルを Tkinter Canvas へ描画する Renderer。

配置の計算は layout.py に任せ、ここでは Canvas への描画だけを行う。
Canvas 座標 = Page 座標を、描画範囲の左上が余白の位置に来るよう平行移動したもの。
"""

from __future__ import annotations

import re
import tkinter as tk

from .geometry import Affine, Point, bounding_frame, contains_point, flatten_path, rect_points
from .layout import bounds_of, layout_page
from .model import Color, Frame, ShapeLayer, SketchLayer, SketchPage, Style, TextLayer

HIGHLIGHT_TAG = "highlight"
HIGHLIGHT_COLOR = "#e53935"
ARTBOARD_BORDER_COLOR = "#b0b0b0"
ARTBOARD_LABEL_COLOR = "#555555"
# 位置確認用の枠線 (スタイルを持たない図形・未対応の Layer) の色
GUIDE_COLOR = "#9e9e9e"

# 子 Layer の座標の基準としてだけ使い、自身は何も描かない Layer
CONTAINER_TYPES = frozenset({"group", "shapeGroup"})


class CanvasRenderer:
    """SketchPage を tkinter.Canvas に描画する。"""

    def __init__(self, canvas: tk.Canvas, margin: float = 40.0) -> None:
        self.canvas = canvas
        self.margin = margin  # 描画範囲の周りの余白 (px)
        self.bounds = Frame()  # 描画範囲 (Page 座標)
        # id(layer) -> Layer の範囲の 4 頂点 (Canvas 座標)
        self._outlines: dict[int, list[Point]] = {}
        # クリックで選択できる Layer と範囲 (前面 -> 背面の順)
        self._hit_targets: list[tuple[SketchLayer, list[Point]]] = []

    # ---- 公開メソッド -------------------------------------------------------

    def render(self, page: SketchPage) -> None:
        """Page を描画する (Sketch の 1pt = 1px)。"""
        self.canvas.delete("all")
        self._outlines.clear()
        self._hit_targets.clear()

        items = layout_page(page)
        self.bounds = bounds_of(items) or Frame()
        # Page 座標 -> Canvas 座標: 描画範囲の左上が (余白, 余白) に来るよう平行移動する
        to_canvas = Affine.translation(self.margin - self.bounds.x, self.margin - self.bounds.y)
        for item in items:
            outline = [to_canvas.apply(*p) for p in item.outline()]
            self._outlines[id(item.layer)] = outline
            self._draw_layer(item.layer, to_canvas @ item.transform, item.style)
            if _is_selectable(item.layer):
                self._hit_targets.append((item.layer, outline))
        self._hit_targets.reverse()

        width = self.bounds.width + self.margin * 2
        height = self.bounds.height + self.margin * 2
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def outline_of(self, layer: SketchLayer) -> list[Point] | None:
        """Layer の範囲を Canvas 座標で返す。描画していない Layer なら None。"""
        return self._outlines.get(id(layer))

    def layer_at(self, x: float, y: float) -> SketchLayer | None:
        """Canvas 座標 (x, y) にある最前面の Layer を返す (Group などの入れ物は除く)。"""
        for layer, outline in self._hit_targets:
            if contains_point(outline, x, y):
                return layer
        return None

    def highlight(self, layer: SketchLayer | None) -> None:
        """Layer の範囲を赤い点線で強調表示する。None なら強調を解除する。"""
        self.canvas.delete(HIGHLIGHT_TAG)
        outline = self.outline_of(layer) if layer is not None else None
        if outline is None:
            return
        self.canvas.create_polygon(
            *_flat(outline), fill="", outline=HIGHLIGHT_COLOR, width=2, dash=(4, 2),
            tags=HIGHLIGHT_TAG,
        )
        self.canvas.tag_raise(HIGHLIGHT_TAG)

    # ---- Layer の種類ごとの描画 ----------------------------------------------
    # transform は Layer のローカル座標 (frame の左上が原点) -> Canvas 座標の変換

    def _draw_layer(self, layer: SketchLayer, transform: Affine, style: Style) -> None:
        if layer.type in CONTAINER_TYPES:
            return
        if layer.is_artboard:
            self._draw_artboard(layer, transform, style)
        elif isinstance(layer, ShapeLayer):
            self._draw_shape(layer, transform, style)
        elif isinstance(layer, TextLayer):
            self._draw_text(layer, transform)
        else:
            self._draw_unsupported(layer, transform)

    def _draw_artboard(self, layer: SketchLayer, transform: Affine, style: Style) -> None:
        """画面の背景 (背景色がなければ白) と、左上に画面の名前を描く。"""
        corners = _transformed_rect(layer, transform)
        self.canvas.create_polygon(
            *_flat(corners), fill=tk_color(style.fill) or "#ffffff", outline=ARTBOARD_BORDER_COLOR,
        )
        x, y = corners[0]
        self.canvas.create_text(
            x, y - 4, text=layer.name, anchor="sw", fill=ARTBOARD_LABEL_COLOR,
            font=("TkDefaultFont", 9),
        )

    def _draw_shape(self, layer: ShapeLayer, transform: Affine, style: Style) -> None:
        points = [transform.apply(*p) for p in shape_outline(layer)]
        if len(points) < 2:
            return
        fill = tk_color(style.fill)
        outline = tk_color(style.border.color) if style.border else ""
        width = max(style.border.thickness, 1.0) if style.border else 1.0
        dash: tuple[int, ...] = ()
        if not fill and not outline:
            # 塗りも線もない図形は Sketch 上では見えないが、位置確認用に点線で示す
            outline, dash = GUIDE_COLOR, (1, 3)

        coords = _flat(points)
        if layer.is_closed:
            self.canvas.create_polygon(*coords, fill=fill, outline=outline, width=width, dash=dash)
            return
        # 開いたパスも、Sketch では始点と終点を結んだ領域が塗られる
        if fill and len(points) >= 3:
            self.canvas.create_polygon(*coords, fill=fill, outline="")
        if outline:
            self.canvas.create_line(*coords, fill=outline, width=width, dash=dash)

    def _draw_text(self, layer: TextLayer, transform: Affine) -> None:
        color = tk_color(layer.color)
        if not layer.text or not color:
            return
        options: dict[str, object] = {
            "text": layer.text,
            "fill": color,
            "font": tk_font(layer.font_name, layer.font_size),
        }
        width = layer.frame.width
        if layer.fixed_width and width > 0:
            # 固定幅のテキストは frame の幅で折り返し、揃え位置に合わせて配置する
            justify = layer.alignment if layer.alignment in ("right", "center") else "left"
            local_x = {"left": 0.0, "center": width / 2, "right": width}[justify]
            anchor = {"left": "nw", "center": "n", "right": "ne"}[justify]
            options.update(width=width, justify=justify)
        else:
            local_x, anchor = 0.0, "nw"
        # Tk の文字列は anchor を中心に回転できる (反転は表現できないため回転だけ反映する)
        angle = round(transform.angle, 3) % 360
        if angle:
            options["angle"] = angle
        x, y = transform.apply(local_x, 0.0)
        self.canvas.create_text(x, y, anchor=anchor, **options)

    def _draw_unsupported(self, layer: SketchLayer, transform: Affine) -> None:
        """未対応の Layer は、点線の枠と名前だけを表示する。"""
        if layer.frame.width <= 0 and layer.frame.height <= 0:
            return
        corners = _transformed_rect(layer, transform)
        self.canvas.create_polygon(*_flat(corners), fill="", outline=GUIDE_COLOR, dash=(2, 2))
        frame = bounding_frame(corners)
        self.canvas.create_text(
            frame.x + 2, frame.y + 2, text=f"{layer.type}: {layer.name}", anchor="nw",
            fill=GUIDE_COLOR, font=("TkDefaultFont", 8),
        )


# ---- 描画用の変換関数 (Tkinter のウィジェットを使わないので単体テストできる) ----------------


def shape_outline(layer: ShapeLayer) -> list[Point]:
    """図形 Layer の輪郭を、ローカル座標の折れ線で返す。"""
    return flatten_path(layer.points, layer.frame.width, layer.frame.height, layer.is_closed)


def tk_font(font_name: str, size: float) -> tuple[object, ...]:
    """Sketch のフォント名 (PostScript 名) を Tkinter のフォント指定に変換する。

    例: ``"Arial-BoldMT"`` -> ``("Arial", -28, "bold")``、
    ``"TimesNewRomanPSMT"`` -> ``("Times New Roman", -16)``。
    サイズは負の値 (ピクセル指定) にして、Sketch の座標系に合わせる。
    """
    family, _, variant = font_name.partition("-")
    family = re.sub(r"(PSMT|MT|PS)$", "", family)
    if " " not in family:
        # "TimesNewRoman" -> "Times New Roman"
        family = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", family)
    spec: list[object] = [family or "TkDefaultFont", -max(1, round(size))]
    variant = variant.lower()
    if any(word in variant for word in ("bold", "black", "heavy", "semibold")):
        spec.append("bold")
    if "italic" in variant or "oblique" in variant:
        spec.append("italic")
    return tuple(spec)


def tk_color(color: Color | None) -> str:
    """Tkinter の色指定に変換する。透明 (alpha = 0) なら空文字 (= 描かない)。

    Tkinter Canvas は半透明を扱えないため、alpha は無視する。
    """
    if color is None or color.alpha <= 0:
        return ""
    return color.to_hex()


def _is_selectable(layer: SketchLayer) -> bool:
    """Canvas のクリックで選択できるか (Group などの入れ物は選択しない)。"""
    return layer.type not in CONTAINER_TYPES


def _transformed_rect(layer: SketchLayer, transform: Affine) -> list[Point]:
    return [transform.apply(x, y) for x, y in rect_points(layer.frame.width, layer.frame.height)]


def _flat(points: list[Point]) -> list[float]:
    """[(x1, y1), (x2, y2)] -> [x1, y1, x2, y2] (Canvas の座標指定の形式)。"""
    return [v for point in points for v in point]
