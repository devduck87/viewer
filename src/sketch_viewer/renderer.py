"""内部モデルを Tkinter Canvas へ描画する Renderer。

座標計算 (layout_page) は Tkinter に依存しない純粋な処理として分離し、
単体テストできるようにしている。
"""

from __future__ import annotations

import base64
import re
import tkinter as tk
from dataclasses import dataclass
from fractions import Fraction

from .geometry import Affine, Point, bounding_frame, flatten_path, layer_transform, rect_points
from .model import (
    BitmapLayer,
    Color,
    Frame,
    ShapeLayer,
    SketchLayer,
    SketchPage,
    Style,
    SymbolInstanceLayer,
    TextLayer,
)

HIGHLIGHT_TAG = "highlight"

# 子 Layer の座標原点としてのみ使い、自身は描画しない Layer
_CONTAINER_TYPES = frozenset({"group", "shapeGroup"})
_ARTBOARD_TYPES = frozenset({"artboard", "symbolMaster"})
# 書き出し範囲を示すだけで、Sketch の描画結果には現れない Layer
_INVISIBLE_TYPES = frozenset({"slice"})
# スタイルを持たない図形を位置確認用に表示する枠線の色
_GUIDE_COLOR = "#9e9e9e"
# 画像拡大時の中間画像の最大辺 (PhotoImage.zoom のメモリ使用量を抑える)
_MAX_ZOOM_SIZE = 4096


@dataclass(frozen=True)
class DrawItem:
    layer: SketchLayer
    frame: Frame  # Page 上の絶対座標での外接矩形
    depth: int
    style: Style  # 描画に使うスタイル (shapeGroup の子は親のスタイルを使う)
    # Layer のローカル座標 (frame 左上が原点) -> Page 座標。回転・反転を含む
    transform: Affine = Affine()

    def outline(self) -> list[Point]:
        """Layer の範囲 (回転・反転後) の 4 頂点を Page 座標で返す。"""
        f = self.layer.frame
        return [self.transform.apply(x, y) for x, y in rect_points(f.width, f.height)]


def layout_page(page: SketchPage) -> list[DrawItem]:
    """表示対象の Layer を描画順 (背面 -> 前面) に並べ、絶対座標を計算する。

    Sketch では子 Layer の frame は親 Layer からの相対座標であり、
    layers 配列は先頭が最背面となる。非表示 Layer は子孫ごと除外する。
    回転・反転は frame の中心を基準に、子 Layer にも引き継がれる。

    shapeGroup では塗り・線が shapeGroup 自身に定義され、子の図形 (rectangle など) は
    形状だけを表すため、子の図形には shapeGroup のスタイルを割り当てる。
    """
    items: list[DrawItem] = []

    def visit(layer: SketchLayer, parent: Affine, depth: int, inherited: Style | None) -> None:
        if not layer.visible:
            return
        transform = parent @ layer_transform(layer)
        f = layer.frame
        frame = bounding_frame([transform.apply(x, y) for x, y in rect_points(f.width, f.height)])
        style = inherited if inherited is not None and not isinstance(layer, TextLayer) else layer.style
        items.append(DrawItem(layer, frame, depth, style, transform))
        child_style = layer.style if layer.type == "shapeGroup" else None
        for child in layer.children:
            visit(child, transform, depth + 1, child_style)

    for layer in page.layers:
        visit(layer, Affine(), 0, None)
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


def shape_outline(layer: ShapeLayer) -> list[Point]:
    """図形 Layer の輪郭をローカル座標の折れ線で返す。"""
    return flatten_path(layer.points, layer.frame.width, layer.frame.height, layer.is_closed)


def image_scale_factors(source: int, target: float) -> tuple[int, int]:
    """PhotoImage.zoom / subsample に渡す整数比 (zoom, subsample) を求める。

    Tkinter の PhotoImage は整数倍の拡大・間引きしかできないため、
    target / source に近い分数で近似する。拡大後の中間画像が大きくなりすぎないよう分母を制限する。
    """
    if source <= 0 or target <= 0:
        return 1, 1
    ratio = Fraction(target / source)
    for limit in (16, 8, 4, 2, 1):
        approx = ratio.limit_denominator(limit)
        if approx > 0 and source * approx.numerator <= _MAX_ZOOM_SIZE:
            return approx.numerator, approx.denominator
    # 大きく縮小する場合
    return 1, max(1, round(source / target))


class CanvasRenderer:
    """SketchPage を tkinter.Canvas に描画する。"""

    def __init__(self, canvas: tk.Canvas, margin: float = 40.0) -> None:
        self.canvas = canvas
        self.margin = margin
        self._outlines: dict[int, list[Point]] = {}  # id(layer) -> Canvas 座標の範囲
        # Canvas 上の画像は参照を保持しないと破棄されるため保持する
        self._photos: list[tk.PhotoImage] = []

    def render(self, page: SketchPage) -> None:
        self.canvas.delete("all")
        self._outlines.clear()
        self._photos.clear()

        items = layout_page(page)
        bounds = bounds_of(items) or Frame()
        to_canvas = Affine.translation(self.margin - bounds.x, self.margin - bounds.y)

        for item in items:
            transform = to_canvas @ item.transform
            self._outlines[id(item.layer)] = [to_canvas.apply(*p) for p in item.outline()]
            self._draw_layer(item.layer, transform, item.style)

        self.canvas.configure(scrollregion=(
            0, 0, bounds.width + self.margin * 2, bounds.height + self.margin * 2,
        ))

    def highlight(self, layer: SketchLayer | None) -> None:
        """指定 Layer の範囲を強調表示する。None なら強調を解除する。"""
        self.canvas.delete(HIGHLIGHT_TAG)
        outline = self._outlines.get(id(layer)) if layer is not None else None
        if outline is None:
            return
        self.canvas.create_polygon(
            *_flat(outline), fill="", outline="#e53935", width=2, dash=(4, 2), tags=HIGHLIGHT_TAG,
        )
        self.canvas.tag_raise(HIGHLIGHT_TAG)

    def _draw_layer(self, layer: SketchLayer, transform: Affine, style: Style) -> None:
        if layer.type in _CONTAINER_TYPES or layer.type in _INVISIBLE_TYPES:
            return
        if layer.type in _ARTBOARD_TYPES:
            self._draw_artboard(layer, transform, style)
        elif isinstance(layer, ShapeLayer):
            self._draw_shape(layer, transform, style)
        elif isinstance(layer, TextLayer):
            self._draw_text(layer, transform)
        elif isinstance(layer, BitmapLayer):
            self._draw_bitmap(layer, transform)
        elif isinstance(layer, SymbolInstanceLayer):
            self._draw_symbol_instance(layer, transform, style)
        else:
            self._draw_unsupported(layer, transform)

    def _draw_artboard(self, layer: SketchLayer, transform: Affine, style: Style) -> None:
        corners = _transformed_rect(layer, transform)
        self.canvas.create_polygon(
            *_flat(corners), fill=_tk_color(style.fill) or "#ffffff", outline="#b0b0b0",
        )
        x, y = corners[0]
        self.canvas.create_text(
            x, y - 4, text=layer.name, anchor="sw", fill="#555555", font=("TkDefaultFont", 9),
        )

    def _draw_shape(self, layer: ShapeLayer, transform: Affine, style: Style) -> None:
        points = [transform.apply(*p) for p in shape_outline(layer)]
        if len(points) < 2:
            return
        fill = _tk_color(style.fill)
        outline = _tk_color(style.border.color) if style.border else ""
        width = max(style.border.thickness, 1.0) if style.border else 1.0
        if not fill and not outline:
            # 塗りも線もない図形は Sketch 上では見えないが、位置確認用に点線で示す
            outline = _GUIDE_COLOR
            dash: tuple[int, ...] = (1, 3)
        else:
            dash = ()

        coords = _flat(points)
        if layer.is_closed:
            self.canvas.create_polygon(*coords, fill=fill, outline=outline, width=width, dash=dash)
            return
        # 開いたパスも Sketch では始点と終点を結んだ領域が塗られる
        if fill and len(points) >= 3:
            self.canvas.create_polygon(*coords, fill=fill, outline="")
        if outline:
            self.canvas.create_line(*coords, fill=outline, width=width, dash=dash)

    def _draw_text(self, layer: TextLayer, transform: Affine) -> None:
        color = _tk_color(layer.color)
        if not layer.text or not color:
            return
        options: dict[str, object] = {
            "text": layer.text,
            "fill": color,
            "font": tk_font(layer.font_name, layer.font_size),
        }
        width = layer.frame.width
        if layer.fixed_width and width > 0:
            # 固定幅テキストは frame の幅で折り返し、揃え位置に合わせて配置する
            justify = layer.alignment if layer.alignment in ("right", "center") else "left"
            local_x = {"left": 0.0, "center": width / 2, "right": width}[justify]
            anchor = {"left": "nw", "center": "n", "right": "ne"}[justify]
            options.update(width=width, justify=justify)
        else:
            local_x, anchor = 0.0, "nw"
        # Tk の文字列は anchor を中心に回転する (反転は表現できないため回転のみ反映)
        angle = round(transform.angle, 3) % 360
        if angle:
            options["angle"] = angle
        x, y = transform.apply(local_x, 0.0)
        self.canvas.create_text(x, y, anchor=anchor, **options)

    def _draw_bitmap(self, layer: BitmapLayer, transform: Affine) -> None:
        photo = self._load_photo(layer, transform)
        if photo is None:
            reason = "画像なし" if layer.image_data is None else "表示できない形式"
            self._draw_unsupported(layer, transform, f"bitmap: {layer.name} ({reason})")
            return
        # Tk の画像は回転できないため、回転後の中心に配置する
        center = transform.apply(layer.frame.width / 2, layer.frame.height / 2)
        self.canvas.create_image(*center, image=photo, anchor="center")
        self._photos.append(photo)

    def _load_photo(self, layer: BitmapLayer, transform: Affine) -> tk.PhotoImage | None:
        if not layer.image_data:
            return None
        try:
            # Tk 8.6 は PNG / GIF に対応 (JPEG などは TclError)
            photo = tk.PhotoImage(master=self.canvas, data=base64.b64encode(layer.image_data))
        except tk.TclError:
            return None
        width, height = round(layer.frame.width), round(layer.frame.height)
        zoom_x, sub_x = image_scale_factors(photo.width(), width)
        zoom_y, sub_y = image_scale_factors(photo.height(), height)
        if zoom_x != 1 or zoom_y != 1:
            photo = photo.zoom(zoom_x, zoom_y)
        # 反転は transform の向きから判定する (負の subsample で左右・上下が反転する)
        flip_x = transform.a < 0 if abs(transform.a) >= abs(transform.c) else transform.c < 0
        flip_y = transform.d < 0 if abs(transform.d) >= abs(transform.b) else transform.b < 0
        if sub_x != 1 or sub_y != 1 or flip_x or flip_y:
            photo = photo.subsample(-sub_x if flip_x else sub_x, -sub_y if flip_y else sub_y)
        return photo

    def _draw_symbol_instance(self, layer: SymbolInstanceLayer, transform: Affine,
                              style: Style) -> None:
        if not layer.resolved:
            self._draw_unsupported(layer, transform, f"symbolInstance: {layer.name} (Symbol なし)")
            return
        # 子 Layer は展開済み。Master の背景色を含める設定のときだけ背景を描く
        fill = _tk_color(style.fill)
        if fill:
            self.canvas.create_polygon(*_flat(_transformed_rect(layer, transform)), fill=fill, outline="")

    def _draw_unsupported(self, layer: SketchLayer, transform: Affine, label: str | None = None) -> None:
        """未対応 (または表示できない) Layer は枠線と名前だけを表示する。"""
        if layer.frame.width <= 0 and layer.frame.height <= 0:
            return
        corners = _transformed_rect(layer, transform)
        self.canvas.create_polygon(*_flat(corners), fill="", outline=_GUIDE_COLOR, dash=(2, 2))
        frame = bounding_frame(corners)
        self.canvas.create_text(
            frame.x + 2, frame.y + 2, text=label or f"{layer.type}: {layer.name}", anchor="nw",
            fill=_GUIDE_COLOR, font=("TkDefaultFont", 8),
        )


def tk_font(font_name: str, size: float) -> tuple[object, ...]:
    """Sketch のフォント名 (PostScript 名) を Tkinter のフォント指定に変換する。

    例: ``"Arial-BoldMT"`` -> ``("Arial", -28, "bold")``、
    ``"TimesNewRomanPSMT"`` -> ``("Times New Roman", -16)``。
    サイズは負値 (ピクセル指定) とし、Sketch の座標系に合わせる。
    """
    family, _, variant = font_name.partition("-")
    family = re.sub(r"(PSMT|MT|PS)$", "", family)
    if " " not in family:
        # "TimesNewRoman" -> "Times New Roman"
        family = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", family)
    spec: list[object] = [family or "TkDefaultFont", -max(1, round(size))]
    lowered = variant.lower()
    if any(word in lowered for word in ("bold", "black", "heavy", "semibold")):
        spec.append("bold")
    if "italic" in lowered or "oblique" in lowered:
        spec.append("italic")
    return tuple(spec)


def _tk_color(color: Color | None) -> str:
    """Tkinter の色指定に変換する。透明 (alpha = 0) なら空文字。

    Tkinter Canvas は半透明を扱えないため alpha は無視する。
    """
    if color is None or color.alpha <= 0:
        return ""
    return color.to_hex()


def _transformed_rect(layer: SketchLayer, transform: Affine) -> list[Point]:
    return [transform.apply(x, y) for x, y in rect_points(layer.frame.width, layer.frame.height)]


def _flat(points: list[Point]) -> list[float]:
    return [v for point in points for v in point]
