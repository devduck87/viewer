"""Sketch Viewer で扱う例外。

いずれも SketchError を基底とし、GUI / CLI では SketchError を捕捉すれば
致命的エラーをまとめて処理できる。
"""


class SketchError(Exception):
    """Sketch データの読み込み・解析に関するエラーの基底クラス。"""


class SketchFileNotFoundError(SketchError):
    """指定されたファイル・ディレクトリが存在しない。"""


class InvalidSketchFileError(SketchError):
    """ZIP として読み込めないなど、Sketch ファイルとして開けない。"""


class MissingEntryError(SketchError):
    """Sketch 内部に要求されたファイル (document.json など) が存在しない。"""


class InvalidJSONError(SketchError):
    """内部ファイルが JSON として不正。"""


class PageNotFoundError(MissingEntryError):
    """document.json が参照する Page JSON が存在しない。"""


class SketchFormatError(SketchError):
    """JSON は読めたが、Sketch として必要な構造を持っていない。"""
