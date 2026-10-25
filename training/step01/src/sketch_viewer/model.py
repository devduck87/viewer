"""Sketch データの内部モデル。

Parser が Sketch JSON をこのモデルへ変換し、利用側はこのモデルだけを扱う。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SketchPage:
    id: str
    name: str


@dataclass
class SketchDocument:
    id: str
    pages: list[SketchPage] = field(default_factory=list)
    source: str = ""  # 読み込んだファイルのパス
