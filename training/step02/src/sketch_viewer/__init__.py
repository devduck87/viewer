"""Sketch Viewer: .sketch ファイルを閲覧する簡易ビューワー。

処理の流れ: Reader -> Parser -> Model
"""

from .errors import SketchError
from .model import Frame, SketchDocument, SketchLayer, SketchPage, format_tree
from .parser import load_document, parse_document
from .reader import DirectorySketchReader, SketchReader, ZipSketchReader, open_reader

__all__ = [
    "DirectorySketchReader",
    "Frame",
    "SketchDocument",
    "SketchError",
    "SketchLayer",
    "SketchPage",
    "SketchReader",
    "ZipSketchReader",
    "format_tree",
    "load_document",
    "open_reader",
    "parse_document",
]
