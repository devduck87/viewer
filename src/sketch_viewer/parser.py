"""Sketch JSON を内部モデルへ変換する Parser。

ファイルへのアクセスはすべて SketchReader を経由する。
未知の Layer や欠けたプロパティは致命的エラーにせず、可能な範囲で読み込む。
"""

from __future__ import annotations

import base64
import binascii
import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import MissingEntryError, PageNotFoundError, SketchError, SketchFormatError
from .geometry import default_points
from .model import (
    SHAPE_LAYER_TYPES,
    BitmapLayer,
    Border,
    Color,
    CurvePoint,
    Frame,
    ShapeLayer,
    SketchDocument,
    SketchLayer,
    SketchPage,
    Style,
    SymbolInstanceLayer,
    TextLayer,
)
from .reader import SketchReader, open_reader

DOCUMENT_JSON = "document.json"

# 背景色を持つ Artboard 系の Layer
_ARTBOARD_TYPES = frozenset({"artboard", "symbolMaster"})
# Sketch の fillType: 0 = 単色 (1 = グラデーション, 4 = パターン, 5 = ノイズ)
_FILL_TYPE_SOLID = 0
# Sketch の paragraphStyle.alignment
_ALIGNMENTS = {0: "left", 1: "right", 2: "center", 3: "justified", 4: "left"}
# Sketch の textBehaviour: 0 = 自動幅, 1 = 固定幅, 2 = 固定サイズ
_TEXT_BEHAVIOUR_AUTO_WIDTH = 0
# "{0.5, 1}" 形式の点
_POINT_PATTERN = re.compile(r"\{\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\}")
# Symbol の入れ子展開の上限 (循環参照対策)
_MAX_SYMBOL_DEPTH = 16


@dataclass
class _Context:
    """解析中に共有する状態。"""

    warnings: list[str] | None = None
    reader: SketchReader | None = None
    # symbolID -> (Symbol Master, instance に背景色を含めるか)
    symbols: dict[str, tuple[SketchLayer, bool]] = field(default_factory=dict)
    # 展開待ちの Symbol Instance
    instances: list[SymbolInstanceLayer] = field(default_factory=list)


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

    document = SketchDocument(id=_str(data.get("do_objectID")), source=str(reader.source))
    context = _Context(document.warnings, reader)
    for ref in page_refs:
        page_path = page_ref_to_path(ref)
        if not reader.exists(page_path):
            raise PageNotFoundError(f"{reader.source}: Page {page_path} が存在しません")
        page_data = reader.read_json(page_path)
        if not isinstance(page_data, dict):
            raise SketchFormatError(f"{page_path}: オブジェクトではありません")
        document.pages.append(_parse_page(page_data, context))

    # ライブラリから取り込んだ Symbol Master (Page には現れない)
    for foreign in _dicts(data.get("foreignSymbols")):
        master = foreign.get("symbolMaster")
        if isinstance(master, dict):
            _parse_layer(master, context)
    _expand_symbols(context)
    return document


def page_ref_to_path(ref: Any) -> str:
    """MSJSONFileReference から内部ファイルパスを得る。

    ``{"_ref": "pages/XXXX"}`` -> ``"pages/XXXX.json"``
    """
    if not isinstance(ref, dict) or not isinstance(ref.get("_ref"), str):
        raise SketchFormatError(f"{DOCUMENT_JSON}: 不正な Page 参照です ({ref!r})")
    path = ref["_ref"]
    return path if path.endswith(".json") else f"{path}.json"


def parse_page(data: dict[str, Any], warnings: list[str] | None = None) -> SketchPage:
    """単独の Page を解析する。Symbol Instance は同じ Page 内の Master だけで解決する。"""
    context = _Context(warnings)
    page = _parse_page(data, context)
    _expand_symbols(context)
    return page


def parse_layer(data: dict[str, Any], warnings: list[str] | None = None) -> SketchLayer:
    """単独の Layer を解析する (画像の読み込み・Symbol の展開は行わない)。"""
    return _parse_layer(data, _Context(warnings))


def _parse_page(data: dict[str, Any], context: _Context) -> SketchPage:
    page = SketchPage(id=_str(data.get("do_objectID")), name=_str(data.get("name")))
    page.layers = _parse_layers(data.get("layers"), page.name, context)
    return page


def _parse_layer(data: dict[str, Any], context: _Context) -> SketchLayer:
    layer_type = _str(data.get("_class"), "unknown")
    common: dict[str, Any] = dict(
        id=_str(data.get("do_objectID")),
        name=_str(data.get("name")),
        type=layer_type,
        frame=parse_frame(data.get("frame")),
        visible=bool(data.get("isVisible", True)),
        style=parse_style(data.get("style")),
        rotation=_num(data.get("rotation")),
        flipped_horizontal=data.get("isFlippedHorizontal") is True,
        flipped_vertical=data.get("isFlippedVertical") is True,
    )
    if layer_type in _ARTBOARD_TYPES and data.get("hasBackgroundColor"):
        common["style"] = Style(fill=parse_color(data.get("backgroundColor")))

    layer: SketchLayer
    if layer_type == "text":
        layer = TextLayer(**common, **_parse_text(data))
    elif layer_type in SHAPE_LAYER_TYPES:
        layer = ShapeLayer(**common, **_parse_shape(data))
    elif layer_type == "bitmap":
        layer = BitmapLayer(**common, image_ref=_image_ref(data.get("image")) or "",
                            image_data=_load_image(data.get("image"), common["name"], context))
    elif layer_type == "symbolInstance":
        overrides = {
            item["overrideName"]: item.get("value")
            for item in _dicts(data.get("overrideValues"))
            if isinstance(item.get("overrideName"), str)
        }
        layer = SymbolInstanceLayer(**common, symbol_id=_str(data.get("symbolID")), overrides=overrides)
        context.instances.append(layer)
    else:
        layer = SketchLayer(**common)

    if layer_type == "symbolMaster" and isinstance(data.get("symbolID"), str):
        include_background = bool(data.get("hasBackgroundColor")) \
            and data.get("includeBackgroundColorInInstance") is True
        context.symbols[data["symbolID"]] = (layer, include_background)

    # Symbol Instance の子は Master から展開する
    if layer_type != "symbolInstance":
        layer.children = _parse_layers(data.get("layers"), layer.name, context)
    return layer


def parse_frame(data: Any) -> Frame:
    if not isinstance(data, dict):
        return Frame()
    return Frame(
        x=_num(data.get("x")),
        y=_num(data.get("y")),
        width=_num(data.get("width")),
        height=_num(data.get("height")),
    )


def parse_color(data: Any) -> Color | None:
    if not isinstance(data, dict):
        return None
    return Color(
        red=_num(data.get("red")),
        green=_num(data.get("green")),
        blue=_num(data.get("blue")),
        alpha=_num(data.get("alpha"), 1.0),
    )


def parse_point(value: Any) -> tuple[float, float] | None:
    """``"{0.5, 1}"`` 形式の文字列を (x, y) に変換する。"""
    match = _POINT_PATTERN.fullmatch(value.strip()) if isinstance(value, str) else None
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
    for item in _dicts(data.get("fills")):
        if item.get("isEnabled", True) and item.get("fillType", _FILL_TYPE_SOLID) == _FILL_TYPE_SOLID:
            fill = parse_color(item.get("color")) or fill

    border = None
    for item in _dicts(data.get("borders")):
        if item.get("isEnabled", True) and item.get("fillType", _FILL_TYPE_SOLID) == _FILL_TYPE_SOLID:
            color = parse_color(item.get("color"))
            if color is not None:
                border = Border(color, _num(item.get("thickness"), 1.0))

    context = data.get("contextSettings")
    opacity = _num(context.get("opacity"), 1.0) if isinstance(context, dict) else 1.0
    return Style(fill=fill, border=border, opacity=opacity)


def _parse_shape(data: dict[str, Any]) -> dict[str, Any]:
    """図形 Layer 固有の情報を ShapeLayer のキーワード引数として返す。"""
    points = []
    for item in _dicts(data.get("points")):
        point = parse_point(item.get("point"))
        if point is None:
            continue
        # hasCurveFrom / hasCurveTo が false の制御点は頂点と同じ位置として扱う
        curve_from = parse_point(item.get("curveFrom")) if item.get("hasCurveFrom") else None
        curve_to = parse_point(item.get("curveTo")) if item.get("hasCurveTo") else None
        points.append(CurvePoint(point, curve_from or point, curve_to or point,
                                 max(0.0, _num(item.get("cornerRadius")))))

    fixed_radius = max(0.0, _num(data.get("fixedRadius")))
    if fixed_radius and not any(p.corner_radius for p in points):
        # 旧形式の角丸は全頂点に同じ半径を適用する
        points = [CurvePoint(p.point, p.curve_from, p.curve_to, fixed_radius) for p in points]
    layer_type = _str(data.get("_class"))
    if not points and layer_type in ("rectangle", "oval"):
        points = default_points(layer_type, fixed_radius)
    return dict(points=points, is_closed=data.get("isClosed", True) is not False,
                fixed_radius=fixed_radius)


def _parse_text(data: dict[str, Any]) -> dict[str, Any]:
    """Text Layer 固有の情報を TextLayer のキーワード引数として返す。"""
    attributed = data.get("attributedString")
    attributed = attributed if isinstance(attributed, dict) else {}

    # 先頭の文字属性を使い、なければ style.textStyle.encodedAttributes で補う
    attrs: dict[str, Any] = {}
    runs = _dicts(attributed.get("attributes"))
    if runs and isinstance(runs[0].get("attributes"), dict):
        attrs = runs[0]["attributes"]
    style = data.get("style")
    text_style = style.get("textStyle") if isinstance(style, dict) else None
    if isinstance(text_style, dict) and isinstance(text_style.get("encodedAttributes"), dict):
        attrs = {**text_style["encodedAttributes"], **attrs}

    font = attrs.get("MSAttributedStringFontAttribute")
    font_attrs = font.get("attributes") if isinstance(font, dict) else None
    font_attrs = font_attrs if isinstance(font_attrs, dict) else {}
    paragraph = attrs.get("paragraphStyle")
    alignment = paragraph.get("alignment") if isinstance(paragraph, dict) else None

    return dict(
        text=_str(attributed.get("string")),
        font_name=_str(font_attrs.get("name")),
        font_size=_num(font_attrs.get("size"), 12.0),
        color=parse_color(attrs.get("MSAttributedStringColorAttribute")) or Color(),
        alignment=_ALIGNMENTS.get(alignment, "left"),
        fixed_width=data.get("textBehaviour", _TEXT_BEHAVIOUR_AUTO_WIDTH) != _TEXT_BEHAVIOUR_AUTO_WIDTH,
    )


def _image_ref(data: Any) -> str | None:
    if isinstance(data, dict) and isinstance(data.get("_ref"), str):
        return data["_ref"]
    return None


def _load_image(data: Any, owner: str, context: _Context) -> bytes | None:
    """MSJSONFileReference (images/ 以下) または埋め込みデータから画像を取得する。"""
    if not isinstance(data, dict):
        return None
    embedded = data.get("data")
    if isinstance(embedded, dict) and isinstance(embedded.get("_data"), str):
        try:
            return base64.b64decode(embedded["_data"])
        except (binascii.Error, ValueError):
            _warn(context.warnings, f"{owner}: 埋め込み画像を復号できません")
            return None
    ref = _image_ref(data)
    if ref is None or context.reader is None:
        return None
    # 拡張子なしで参照されている場合もある
    for name in (ref, f"{ref}.png"):
        if context.reader.exists(name):
            try:
                return context.reader.read_image(name)
            except SketchError as exc:
                _warn(context.warnings, f"{owner}: 画像を読み込めません ({exc})")
                return None
    _warn(context.warnings, f"{owner}: 画像 {ref} が存在しません")
    return None


def _expand_symbols(context: _Context) -> None:
    """すべての Symbol Instance に参照先 Master の内容を展開する。"""
    for instance in context.instances:
        _expand_instance(instance, {}, context, ())


def _expand_instance(instance: SymbolInstanceLayer, inherited: dict[str, dict[str, Any]],
                     context: _Context, stack: tuple[str, ...]) -> None:
    """instance.children に Master の子 Layer の複製を展開し、Override を適用する。

    inherited は外側の instance から渡された Override で、instance 自身の Override より優先する。
    キーは instance から見た Layer ID のパス ("ID" または "入れ子 instance ID/ID")。
    """
    overrides: dict[str, dict[str, Any]] = {}
    for name, value in instance.overrides.items():
        if "_" in name:
            path, _, prop = name.rpartition("_")
            overrides.setdefault(path, {})[prop] = value
    for path, values in inherited.items():
        overrides[path] = {**overrides.get(path, {}), **values}

    instance.children, instance.resolved = [], False
    entry = context.symbols.get(instance.symbol_id)
    if entry is None:
        _warn(context.warnings, f"{instance.name}: Symbol {instance.symbol_id} が見つかりません")
        return
    if instance.symbol_id in stack or len(stack) >= _MAX_SYMBOL_DEPTH:
        _warn(context.warnings, f"{instance.name}: Symbol が循環参照しています")
        return

    master, include_background = entry
    children = copy.deepcopy(master.children)
    # Master と instance の大きさが異なる場合は子 Layer を比例して伸縮する
    sx = instance.frame.width / master.frame.width if master.frame.width else 1.0
    sy = instance.frame.height / master.frame.height if master.frame.height else 1.0
    if sx != 1.0 or sy != 1.0:
        for child in children:
            _scale_layer(child, sx, sy)
    instance.children, instance.resolved = children, True
    if include_background:
        instance.style = Style(fill=master.style.fill)

    stack = (*stack, instance.symbol_id)

    def visit(layer: SketchLayer) -> None:
        values = overrides.get(layer.id, {})
        if isinstance(layer, TextLayer) and isinstance(values.get("stringValue"), str):
            layer.text = values["stringValue"]
        if isinstance(layer, BitmapLayer) and _image_ref(values.get("image")):
            layer.image_ref = _image_ref(values["image"]) or ""
            layer.image_data = _load_image(values["image"], layer.name, context)
        if isinstance(layer, SymbolInstanceLayer):
            symbol_id = values.get("symbolID")
            if symbol_id == "":
                # 空の symbolID は「なし」に差し替えられた入れ子 Symbol
                layer.visible = False
            elif isinstance(symbol_id, str):
                layer.symbol_id = symbol_id
            prefix = f"{layer.id}/"
            nested = {path[len(prefix):]: v for path, v in overrides.items() if path.startswith(prefix)}
            _expand_instance(layer, nested, context, stack)
            return
        for child in layer.children:
            visit(child)

    for child in children:
        visit(child)


def _scale_layer(layer: SketchLayer, sx: float, sy: float) -> None:
    """frame を親の伸縮率に合わせて変更する (文字サイズは変えない)。"""
    f = layer.frame
    layer.frame = Frame(f.x * sx, f.y * sy, f.width * sx, f.height * sy)
    for child in layer.children:
        _scale_layer(child, sx, sy)


def _dicts(items: Any) -> list[dict[str, Any]]:
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _parse_layers(items: Any, owner: str, context: _Context) -> list[SketchLayer]:
    if items is None:
        return []
    if not isinstance(items, list):
        _warn(context.warnings, f"{owner}: layers が配列ではないため無視しました")
        return []
    layers = []
    for item in items:
        if isinstance(item, dict):
            layers.append(_parse_layer(item, context))
        else:
            _warn(context.warnings, f"{owner}: 不正な Layer データを無視しました ({item!r:.40})")
    return layers


def _warn(warnings: list[str] | None, message: str) -> None:
    if warnings is not None:
        warnings.append(message)


def _str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _num(value: Any, default: float = 0.0) -> float:
    # bool は int のサブクラスなので除外する
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default
