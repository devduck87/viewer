"""Symbol Instance に Symbol Master の内容を展開する。

Sketch の Symbol Instance は参照先の symbolID だけを持ち、子 Layer を持たない。
そこで読み込みの最後に、Master の子 Layer を複製して instance の children に入れ、
Override (文字列・画像・入れ子 Symbol の差し替え) を適用する。

Override のキーは "<Layer ID のパス>_<プロパティ名>" の形をしている。

- ``"ABC_stringValue"``      : instance 内の Layer ABC の文字列
- ``"N1/ABC_stringValue"``   : instance 内の入れ子 instance N1 の中の Layer ABC の文字列
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .images import image_ref, load_image
from .model import BitmapLayer, Frame, SketchLayer, Style, SymbolInstanceLayer, TextLayer
from .reader import SketchReader

# 入れ子展開の上限 (循環参照対策)
MAX_SYMBOL_DEPTH = 16

# Layer ID のパス -> {プロパティ名: 値}
Overrides = dict[str, dict[str, Any]]


@dataclass
class _Master:
    layer: SketchLayer
    include_background: bool  # instance にも Master の背景色を描くか


class SymbolResolver:
    """Symbol Master と Symbol Instance を集めておき、最後にまとめて展開する。

    Instance が Master より先に現れることもあるため、展開は全 Layer を読み終えてから行う。
    """

    def __init__(self, reader: SketchReader | None = None,
                 warnings: list[str] | None = None) -> None:
        self.reader = reader  # 画像の Override を読み込むために使う
        self.warnings = warnings if warnings is not None else []
        self._masters: dict[str, _Master] = {}
        self._instances: list[SymbolInstanceLayer] = []

    def add_master(self, symbol_id: str, layer: SketchLayer, include_background: bool) -> None:
        self._masters[symbol_id] = _Master(layer, include_background)

    def add_instance(self, instance: SymbolInstanceLayer) -> None:
        self._instances.append(instance)

    def expand_all(self) -> None:
        """登録済みのすべての Symbol Instance を展開する。"""
        for instance in self._instances:
            self._expand(instance, inherited={}, stack=())

    def _expand(self, instance: SymbolInstanceLayer, inherited: Overrides,
                stack: tuple[str, ...]) -> None:
        """instance.children に Master の子 Layer の複製を入れ、Override を適用する。

        inherited は外側の instance から渡された Override で、instance 自身の Override より優先する。
        stack は展開中の symbolID の並び (循環参照の検出に使う)。
        """
        overrides = _merge_overrides(_split_overrides(instance.overrides), inherited)
        instance.children, instance.resolved = [], False

        master = self._masters.get(instance.symbol_id)
        if master is None:
            self.warnings.append(f"{instance.name}: Symbol {instance.symbol_id} が見つかりません")
            return
        if instance.symbol_id in stack or len(stack) >= MAX_SYMBOL_DEPTH:
            self.warnings.append(f"{instance.name}: Symbol が循環参照しています")
            return

        instance.children = _copy_children(master.layer, instance.frame)
        instance.resolved = True
        if master.include_background:
            instance.style = Style(fill=master.layer.style.fill)

        stack = (*stack, instance.symbol_id)
        for child in instance.children:
            self._apply_overrides(child, overrides, stack)

    def _apply_overrides(self, layer: SketchLayer, overrides: Overrides,
                         stack: tuple[str, ...]) -> None:
        """layer とその子孫に Override を適用する。入れ子の instance はここで展開する。"""
        values = overrides.get(layer.id, {})

        if isinstance(layer, TextLayer) and isinstance(values.get("stringValue"), str):
            layer.text = values["stringValue"]

        if isinstance(layer, BitmapLayer) and image_ref(values.get("image")):
            layer.image_ref = image_ref(values["image"]) or ""
            layer.image_data = load_image(values["image"], layer.name, self.reader, self.warnings)

        if isinstance(layer, SymbolInstanceLayer):
            _swap_symbol(layer, values.get("symbolID"))
            self._expand(layer, _overrides_for_nested(overrides, layer.id), stack)
            return

        for child in layer.children:
            self._apply_overrides(child, overrides, stack)


def _split_overrides(raw: dict[str, object]) -> Overrides:
    """``{"ABC_stringValue": "x"}`` を ``{"ABC": {"stringValue": "x"}}`` に変換する。"""
    result: Overrides = {}
    for name, value in raw.items():
        if "_" in name:
            path, _, prop = name.rpartition("_")
            result.setdefault(path, {})[prop] = value
    return result


def _merge_overrides(own: Overrides, inherited: Overrides) -> Overrides:
    """instance 自身の Override に、外側から渡された Override を上書きする。"""
    merged = dict(own)
    for path, values in inherited.items():
        merged[path] = {**merged.get(path, {}), **values}
    return merged


def _overrides_for_nested(overrides: Overrides, nested_id: str) -> Overrides:
    """入れ子の instance 宛ての Override を取り出し、パスの先頭 "<nested_id>/" を外す。"""
    prefix = f"{nested_id}/"
    return {path[len(prefix):]: values
            for path, values in overrides.items() if path.startswith(prefix)}


def _swap_symbol(instance: SymbolInstanceLayer, symbol_id: object) -> None:
    """入れ子 Symbol の差し替え (symbolID の Override) を適用する。"""
    if symbol_id == "":
        # 空の symbolID は「なし」に差し替えられた入れ子 Symbol
        instance.visible = False
    elif isinstance(symbol_id, str):
        instance.symbol_id = symbol_id


def _copy_children(master: SketchLayer, instance_frame: Frame) -> list[SketchLayer]:
    """Master の子 Layer を複製する。instance と大きさが違えば比例して伸縮する。"""
    children = copy.deepcopy(master.children)
    sx = instance_frame.width / master.frame.width if master.frame.width else 1.0
    sy = instance_frame.height / master.frame.height if master.frame.height else 1.0
    if sx != 1.0 or sy != 1.0:
        for child in children:
            _scale_layer(child, sx, sy)
    return children


def _scale_layer(layer: SketchLayer, sx: float, sy: float) -> None:
    """layer と子孫の frame を伸縮する (文字サイズは変えない)。"""
    f = layer.frame
    layer.frame = Frame(f.x * sx, f.y * sy, f.width * sx, f.height * sy)
    for child in layer.children:
        _scale_layer(child, sx, sy)
