"""Sketch JSON を内部モデルへ変換する Parser。

読み込みの流れ:
    document.json -> pages/*.json -> 各 Page の layers を再帰的に解析

ファイルへのアクセスはすべて SketchReader を経由する。
未知の Layer や欠けたプロパティは致命的エラーにせず、可能な範囲で読み込む。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import MissingEntryError, PageNotFoundError, SketchFormatError
from .geometry import default_points
from .model import (
    ARTBOARD_LAYER_TYPES,
    SHAPE_LAYER_TYPES,
    Border,
    Color,
    CurvePoint,
    Frame,
    ShapeLayer,
    SketchDocument,
    SketchLayer,
    SketchPage,
    Style,
    TextLayer,
)
from .reader import SketchReader, open_reader

DOCUMENT_JSON = "document.json"

# Sketch の fillType: 0 = 単色 (1 = グラデーション, 4 = パターン, 5 = ノイズ)
FILL_TYPE_SOLID = 0
# Sketch の paragraphStyle.alignment
TEXT_ALIGNMENTS = {0: "left", 1: "right", 2: "center", 3: "justified", 4: "left"}
# Sketch の textBehaviour: 0 = 自動幅, 1 = 固定幅, 2 = 固定サイズ
TEXT_BEHAVIOUR_AUTO_WIDTH = 0
# "{0.5, 1}" 形式の点
POINT_PATTERN = re.compile(r"\{\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\}")


@dataclass
class ParseContext:
    """解析中に共有する状態。"""

    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


# ---- Document / Page ----------------------------------------------------


def load_document(path: str | Path) -> SketchDocument:
    """``.sketch`` ファイルまたは展開済みディレクトリを読み込む。"""
    with open_reader(path) as reader:
        return parse_document(reader)


def parse_document(reader: SketchReader) -> SketchDocument:
    """document.json と参照先の Page JSON を読み込み SketchDocument を返す。"""
    if not reader.exists(DOCUMENT_JSON):
        raise MissingEntryError(f"{reader.source}: {DOCUMENT_JSON} が存在しません")
    data = reader.read_json(DOCUMENT_JSON)
    if not isinstance(data, dict):
        raise SketchFormatError(f"{DOCUMENT_JSON}: オブジェクトではありません")
    page_refs = data.get("pages", [])
    if not isinstance(page_refs, list):
        raise SketchFormatError(f"{DOCUMENT_JSON}: pages が配列ではありません")

    document = SketchDocument(id=_as_str(data.get("do_objectID")), source=str(reader.source))
    context = ParseContext(document.warnings)
    for ref in page_refs:
        page_data = _read_page_json(reader, page_ref_to_path(ref))
        document.pages.append(_parse_page(page_data, context))
    return document


def page_ref_to_path(ref: Any) -> str:
    """Page の参照から内部ファイルのパスを得る。

    ``{"_ref": "pages/XXXX"}`` -> ``"pages/XXXX.json"``
    """
    if not isinstance(ref, dict) or not isinstance(ref.get("_ref"), str):
        raise SketchFormatError(f"{DOCUMENT_JSON}: 不正な Page 参照です ({ref!r})")
    path = ref["_ref"]
    return path if path.endswith(".json") else f"{path}.json"


def parse_page(data: dict[str, Any], warnings: list[str] | None = None) -> SketchPage:
    """単独の Page を解析する。"""
    return _parse_page(data, ParseContext([] if warnings is None else warnings))


def _read_page_json(reader: SketchReader, page_path: str) -> dict[str, Any]:
    if not reader.exists(page_path):
        raise PageNotFoundError(f"{reader.source}: Page {page_path} が存在しません")
    data = reader.read_json(page_path)
    if not isinstance(data, dict):
        raise SketchFormatError(f"{page_path}: オブジェクトではありません")
    return data


def _parse_page(data: dict[str, Any], context: ParseContext) -> SketchPage:
    name = _as_str(data.get("name"))
    layers = _parse_layers(data.get("layers"), name, context)
    return SketchPage(id=_as_str(data.get("do_objectID")), name=name, layers=layers)


# ---- Layer --------------------------------------------------------------


def parse_layer(data: dict[str, Any], warnings: list[str] | None = None) -> SketchLayer:
    """単独の Layer を解析する。"""
    return _parse_layer(data, ParseContext([] if warnings is None else warnings))


def _parse_layers(items: Any, owner: str, context: ParseContext) -> list[SketchLayer]:
    """layers 配列を解析する。owner は警告メッセージに使う親の名前。"""
    if items is None:
        return []
    if not isinstance(items, list):
        context.warn(f"{owner}: layers が配列ではないため無視しました")
        return []
    layers = []
    for item in items:
        if isinstance(item, dict):
            layers.append(_parse_layer(item, context))
        else:
            context.warn(f"{owner}: 不正な Layer データを無視しました ({item!r:.40})")
    return layers


def _parse_layer(data: dict[str, Any], context: ParseContext) -> SketchLayer:
    layer_type = _as_str(data.get("_class"), "unknown")
    common = _parse_common(data, layer_type)

    layer: SketchLayer
    if layer_type == "text":
        layer = TextLayer(**common, **_parse_text(data))
    elif layer_type in SHAPE_LAYER_TYPES:
        layer = ShapeLayer(**common, **_parse_shape(data))
    else:
        layer = SketchLayer(**common)

    layer.children = _parse_layers(data.get("layers"), layer.name, context)
    return layer


def _parse_common(data: dict[str, Any], layer_type: str) -> dict[str, Any]:
    """すべての Layer に共通する情報を SketchLayer のキーワード引数として返す。"""
    style = parse_style(data.get("style"))
    if layer_type in ARTBOARD_LAYER_TYPES and data.get("hasBackgroundColor"):
        # Artboard の背景色は style ではなく backgroundColor に入っている
        style = Style(fill=parse_color(data.get("backgroundColor")))
    return dict(
        id=_as_str(data.get("do_objectID")),
        name=_as_str(data.get("name")),
        type=layer_type,
        frame=parse_frame(data.get("frame")),
        visible=bool(data.get("isVisible", True)),
        style=style,
        rotation=_as_float(data.get("rotation")),
        flipped_horizontal=data.get("isFlippedHorizontal") is True,
        flipped_vertical=data.get("isFlippedVertical") is True,
    )


def _parse_text(data: dict[str, Any]) -> dict[str, Any]:
    """Text Layer 固有の情報を TextLayer のキーワード引数として返す。"""
    attributed = _as_dict(data.get("attributedString"))
    attrs = _text_attributes(data, attributed)
    font_attrs = _as_dict(_as_dict(attrs.get("MSAttributedStringFontAttribute")).get("attributes"))
    alignment = _as_dict(attrs.get("paragraphStyle")).get("alignment")
    return dict(
        text=_as_str(attributed.get("string")),
        font_name=_as_str(font_attrs.get("name")),
        font_size=_as_float(font_attrs.get("size"), 12.0),
        color=parse_color(attrs.get("MSAttributedStringColorAttribute")) or Color(),
        alignment=TEXT_ALIGNMENTS.get(alignment, "left"),
        fixed_width=data.get("textBehaviour", TEXT_BEHAVIOUR_AUTO_WIDTH) != TEXT_BEHAVIOUR_AUTO_WIDTH,
    )


def _text_attributes(data: dict[str, Any], attributed: dict[str, Any]) -> dict[str, Any]:
    """先頭の文字の属性を返す。足りない属性は style.textStyle の既定値で補う。"""
    runs = _dict_items(attributed.get("attributes"))
    first_run = _as_dict(runs[0].get("attributes")) if runs else {}
    text_style = _as_dict(_as_dict(data.get("style")).get("textStyle"))
    defaults = _as_dict(text_style.get("encodedAttributes"))
    return {**defaults, **first_run}


def _parse_shape(data: dict[str, Any]) -> dict[str, Any]:
    """図形 Layer 固有の情報を ShapeLayer のキーワード引数として返す。"""
    points = [p for p in map(_parse_curve_point, _dict_items(data.get("points"))) if p is not None]

    fixed_radius = max(0.0, _as_float(data.get("fixedRadius")))
    if fixed_radius and not any(p.corner_radius for p in points):
        # 古い形式の角丸は、全頂点に同じ半径を適用する
        points = [CurvePoint(p.point, p.curve_from, p.curve_to, fixed_radius) for p in points]

    layer_type = _as_str(data.get("_class"))
    if not points and layer_type in ("rectangle", "oval"):
        # points を持たない古い形式の rectangle / oval
        points = default_points(layer_type, fixed_radius)

    return dict(points=points, is_closed=data.get("isClosed", True) is not False,
                fixed_radius=fixed_radius)


def _parse_curve_point(data: dict[str, Any]) -> CurvePoint | None:
    point = parse_point(data.get("point"))
    if point is None:
        return None
    # hasCurveFrom / hasCurveTo が false の制御点は、頂点と同じ位置として扱う
    curve_from = parse_point(data.get("curveFrom")) if data.get("hasCurveFrom") else None
    curve_to = parse_point(data.get("curveTo")) if data.get("hasCurveTo") else None
    corner_radius = max(0.0, _as_float(data.get("cornerRadius")))
    return CurvePoint(point, curve_from or point, curve_to or point, corner_radius)


# ---- 値の変換 -----------------------------------------------------------


def parse_frame(data: Any) -> Frame:
    data = _as_dict(data)
    return Frame(
        x=_as_float(data.get("x")),
        y=_as_float(data.get("y")),
        width=_as_float(data.get("width")),
        height=_as_float(data.get("height")),
    )


def parse_color(data: Any) -> Color | None:
    if not isinstance(data, dict):
        return None
    return Color(
        red=_as_float(data.get("red")),
        green=_as_float(data.get("green")),
        blue=_as_float(data.get("blue")),
        alpha=_as_float(data.get("alpha"), 1.0),
    )


def parse_point(value: Any) -> tuple[float, float] | None:
    """``"{0.5, 1}"`` 形式の文字列を (x, y) に変換する。不正なら None。"""
    match = POINT_PATTERN.fullmatch(value.strip()) if isinstance(value, str) else None
    if match is None:
        return None
    try:
        return float(match.group(1)), float(match.group(2))
    except ValueError:
        return None


def parse_style(data: Any) -> Style:
    """fill / border / opacity を取得する。

    Sketch の fills / borders は配列の末尾が最前面。有効な単色のうち最前面のものを使う。
    """
    if not isinstance(data, dict):
        return Style()

    fill = None
    for item in _solid_paints(data.get("fills")):
        fill = parse_color(item.get("color")) or fill

    border = None
    for item in _solid_paints(data.get("borders")):
        color = parse_color(item.get("color"))
        if color is not None:
            border = Border(color, _as_float(item.get("thickness"), 1.0))

    opacity = _as_float(_as_dict(data.get("contextSettings")).get("opacity"), 1.0)
    return Style(fill=fill, border=border, opacity=opacity)


def _solid_paints(items: Any) -> list[dict[str, Any]]:
    """fills / borders のうち、有効な単色のものだけを返す。"""
    return [
        item for item in _dict_items(items)
        if item.get("isEnabled", True) and item.get("fillType", FILL_TYPE_SOLID) == FILL_TYPE_SOLID
    ]


# ---- 型を確かめるための小さな関数 -------------------------------------------
# Sketch JSON は値が欠けていたり型が違ったりすることがあるため、
# 想定外の値は既定値に置き換えて読み込みを続ける。


def _as_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_float(value: Any, default: float = 0.0) -> float:
    # bool は int のサブクラスなので除外する
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_items(items: Any) -> list[dict[str, Any]]:
    """配列のうち、オブジェクト (dict) の要素だけを返す。配列でなければ空リスト。"""
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
