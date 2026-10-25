"""内部モデルを Tkinter Canvas へ描画する Renderer。

配置の計算は layout.py に任せ、ここでは Canvas への描画だけを行う。
Canvas 座標 = Page 座標を、描画範囲の左上が余白の位置に来るよう平行移動したもの。
"""

from __future__ import annotations

import re
import tkinter as tk

from .layout import bounds_of, layout_page
from .model import Color, Frame, SketchLayer, SketchPage, TextLayer

HIGHLIGHT_TAG = "highlight"
HIGHLIGHT_COLOR = "#e53935"
ARTBOARD_BORDER_COLOR = "#b0b0b0"
ARTBOARD_LABEL_COLOR = "#555555"
# 位置確認用の枠線 (スタイルを持たない図形・未対応の Layer) の色
GUIDE_COLOR = "#9e9e9e"

# 子 Layer の座標の基準としてだけ使い、自身は何も描かない Layer
CONTAINER_TYPES = frozenset({"group"})


class CanvasRenderer:
    """SketchPage を tkinter.Canvas に描画する。"""

    def __init__(self, canvas: tk.Canvas, margin: float = 40.0) -> None:
        self.canvas = canvas
        self.margin = margin  # 描画範囲の周りの余白 (px)
        self.bounds = Frame()  # 描画範囲 (Page 座標)
        # id(layer) -> Layer の範囲 (Canvas 座標)
        self._frames: dict[int, Frame] = {}

    # ---- 公開メソッド -------------------------------------------------------

    def render(self, page: SketchPage) -> None:
        """Page を描画する (Sketch の 1pt = 1px)。"""
        self.canvas.delete("all")
        self._frames.clear()

        items = layout_page(page)
        self.bounds = bounds_of(items) or Frame()
        # Page 座標 -> Canvas 座標: 描画範囲の左上が (余白, 余白) に来るよう平行移動する
        dx, dy = self.margin - self.bounds.x, self.margin - self.bounds.y
        for item in items:
            frame = item.frame.offset(dx, dy)
            self._frames[id(item.layer)] = frame
            self._draw_layer(item.layer, frame)

        width = self.bounds.width + self.margin * 2
        height = self.bounds.height + self.margin * 2
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def frame_of(self, layer: SketchLayer) -> Frame | None:
        """Layer の範囲を Canvas 座標で返す。描画していない Layer なら None。"""
        return self._frames.get(id(layer))

    def highlight(self, layer: SketchLayer | None) -> None:
        """Layer の範囲を赤い点線で強調表示する。None なら強調を解除する。"""
        self.canvas.delete(HIGHLIGHT_TAG)
        frame = self.frame_of(layer) if layer is not None else None
        if frame is None:
            return
        self.canvas.create_rectangle(
            frame.x, frame.y, frame.right, frame.bottom,
            outline=HIGHLIGHT_COLOR, width=2, dash=(4, 2), tags=HIGHLIGHT_TAG,
        )
        self.canvas.tag_raise(HIGHLIGHT_TAG)

    # ---- Layer の種類ごとの描画 ----------------------------------------------
    # frame は Layer の範囲 (Canvas 座標)

    def _draw_layer(self, layer: SketchLayer, frame: Frame) -> None:
        if layer.type in CONTAINER_TYPES:
            return
        if layer.is_artboard:
            self._draw_artboard(layer, frame)
        elif layer.type in ("rectangle", "oval"):
            self._draw_shape(layer, frame)
        elif isinstance(layer, TextLayer):
            self._draw_text(layer, frame)
        else:
            self._draw_unsupported(layer, frame)

    def _draw_artboard(self, layer: SketchLayer, frame: Frame) -> None:
        """画面の背景 (背景色がなければ白) と、左上に画面の名前を描く。"""
        self.canvas.create_rectangle(
            frame.x, frame.y, frame.right, frame.bottom,
            fill=tk_color(layer.style.fill) or "#ffffff", outline=ARTBOARD_BORDER_COLOR,
        )
        self.canvas.create_text(
            frame.x, frame.y - 4, text=layer.name, anchor="sw", fill=ARTBOARD_LABEL_COLOR,
            font=("TkDefaultFont", 9),
        )

    def _draw_shape(self, layer: SketchLayer, frame: Frame) -> None:
        """rectangle / oval を frame いっぱいに描く。"""
        style = layer.style
        fill = tk_color(style.fill)
        outline = tk_color(style.border.color) if style.border else ""
        width = max(style.border.thickness, 1.0) if style.border else 1.0
        dash: tuple[int, ...] = ()
        if not fill and not outline:
            # 塗りも線もない図形は Sketch 上では見えないが、位置確認用に点線で示す
            outline, dash = GUIDE_COLOR, (1, 3)

        create = self.canvas.create_oval if layer.type == "oval" else self.canvas.create_rectangle
        create(frame.x, frame.y, frame.right, frame.bottom,
               fill=fill, outline=outline, width=width, dash=dash)

    def _draw_text(self, layer: TextLayer, frame: Frame) -> None:
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
        self.canvas.create_text(frame.x + local_x, frame.y, anchor=anchor, **options)

    def _draw_unsupported(self, layer: SketchLayer, frame: Frame) -> None:
        """未対応の Layer は、点線の枠と名前だけを表示する。"""
        if frame.width <= 0 and frame.height <= 0:
            return
        self.canvas.create_rectangle(
            frame.x, frame.y, frame.right, frame.bottom, outline=GUIDE_COLOR, dash=(2, 2),
        )
        self.canvas.create_text(
            frame.x + 2, frame.y + 2, text=f"{layer.type}: {layer.name}", anchor="nw",
            fill=GUIDE_COLOR, font=("TkDefaultFont", 8),
        )


# ---- 描画用の変換関数 (Tkinter のウィジェットを使わないので単体テストできる) ----------------


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
