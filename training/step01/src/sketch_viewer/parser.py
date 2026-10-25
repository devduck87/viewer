"""Sketch JSON を内部モデルへ変換する Parser。

読み込みの流れ:
    document.json -> pages/*.json

ファイルへのアクセスはすべて SketchReader を経由する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import MissingEntryError, PageNotFoundError, SketchFormatError
from .model import SketchDocument, SketchPage
from .reader import SketchReader, open_reader

DOCUMENT_JSON = "document.json"


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
    for ref in page_refs:
        page_data = _read_page_json(reader, page_ref_to_path(ref))
        document.pages.append(_parse_page(page_data))
    return document


def page_ref_to_path(ref: Any) -> str:
    """Page の参照から内部ファイルのパスを得る。

    ``{"_ref": "pages/XXXX"}`` -> ``"pages/XXXX.json"``
    """
    if not isinstance(ref, dict) or not isinstance(ref.get("_ref"), str):
        raise SketchFormatError(f"{DOCUMENT_JSON}: 不正な Page 参照です ({ref!r})")
    path = ref["_ref"]
    return path if path.endswith(".json") else f"{path}.json"


def _read_page_json(reader: SketchReader, page_path: str) -> dict[str, Any]:
    if not reader.exists(page_path):
        raise PageNotFoundError(f"{reader.source}: Page {page_path} が存在しません")
    data = reader.read_json(page_path)
    if not isinstance(data, dict):
        raise SketchFormatError(f"{page_path}: オブジェクトではありません")
    return data


def _parse_page(data: dict[str, Any]) -> SketchPage:
    return SketchPage(id=_as_str(data.get("do_objectID")), name=_as_str(data.get("name")))


# ---- 型を確かめるための小さな関数 -------------------------------------------
# Sketch JSON は値が欠けていたり型が違ったりすることがあるため、
# 想定外の値は既定値に置き換えて読み込みを続ける。


def _as_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default
