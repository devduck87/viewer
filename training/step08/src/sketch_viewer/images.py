"""Bitmap Layer の画像データの取得。

Sketch の画像は 2 通りの形で保存されている。

- ``{"_ref": "images/xxxx.png"}``: Sketch ファイル内の別ファイルを参照する
- ``{"data": {"_data": "<base64>"}}``: JSON に直接埋め込まれている
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

from .errors import SketchError
from .reader import SketchReader


def image_ref(data: Any) -> str | None:
    """画像の参照 (``{"_ref": "images/xxxx.png"}``) からファイル名を取り出す。"""
    if isinstance(data, dict) and isinstance(data.get("_ref"), str):
        return data["_ref"]
    return None


def load_image(data: Any, owner: str, reader: SketchReader | None,
               warnings: list[str]) -> bytes | None:
    """画像データを返す。読み込めなければ warnings に理由を追加して None を返す。

    owner は警告メッセージに使う Layer 名。reader が None なら参照先の画像は読まない。
    """
    if not isinstance(data, dict):
        return None

    embedded = data.get("data")
    if isinstance(embedded, dict) and isinstance(embedded.get("_data"), str):
        try:
            return base64.b64decode(embedded["_data"])
        except (binascii.Error, ValueError):
            warnings.append(f"{owner}: 埋め込み画像を復号できません")
            return None

    ref = image_ref(data)
    if ref is None or reader is None:
        return None
    # 拡張子なしで参照されている場合もある
    for name in (ref, f"{ref}.png"):
        if reader.exists(name):
            try:
                return reader.read_image(name)
            except SketchError as exc:
                warnings.append(f"{owner}: 画像を読み込めません ({exc})")
                return None
    warnings.append(f"{owner}: 画像 {ref} が存在しません")
    return None
