"""Sketch JSON を内部モデルへ変換する Parser。

読み込みの流れ:
    document.json -> pages/*.json -> 各 Page の layers を再帰的に解析

ファイルへのアクセスはすべて SketchReader を経由する。
未知の Layer や欠けたプロパティは致命的エラーにせず、可能な範囲で読み込む。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import MissingEntryError, PageNotFoundError, SketchFormatError
from .model import Frame, SketchDocument, SketchLayer, SketchPage
from .reader import SketchReader, open_reader

DOCUMENT_JSON = "document.json"


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
    layer = SketchLayer(
        id=_as_str(data.get("do_objectID")),
        name=_as_str(data.get("name")),
        type=_as_str(data.get("_class"), "unknown"),
        frame=parse_frame(data.get("frame")),
        visible=bool(data.get("isVisible", True)),
    )
    layer.children = _parse_layers(data.get("layers"), layer.name, context)
    return layer


# ---- 値の変換 -----------------------------------------------------------


def parse_frame(data: Any) -> Frame:
    data = _as_dict(data)
    return Frame(
        x=_as_float(data.get("x")),
        y=_as_float(data.get("y")),
        width=_as_float(data.get("width")),
        height=_as_float(data.get("height")),
    )


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
