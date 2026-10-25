"""選択した Layer のプロパティ (位置・サイズ・色など) を表示する欄。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .layout import placement_of
from .model import Color, SketchLayer, SketchPage, TextLayer

# プロパティ欄の行: (表示名, [(キー, 値の前に付ける見出し), ...])
INFO_ROWS = (
    ("名前", [("name", "")]),
    ("種類", [("type", "")]),
    ("画面", [("artboard", "")]),
    ("位置", [("x", "X"), ("y", "Y")]),
    ("サイズ", [("width", "W"), ("height", "H")]),
    ("回転", [("rotation", "")]),
    ("塗り", [("fill", "")]),
    ("線", [("border", "")]),
    ("文字色", [("text_color", "")]),
    ("フォント", [("font", "")]),
)
# 色見本を表示する項目
COLOR_KEYS = ("fill", "border", "text_color")
FIELD_KEYS = tuple(key for _, fields in INFO_ROWS for key, _ in fields)


def format_number(value: float) -> str:
    """座標などを小数第 2 位までの短い文字列にする (例: 12.0 -> "12"、-0.001 -> "0")。"""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def format_color(color: Color) -> str:
    """``#RRGGBB`` 形式にする。半透明なら不透明度を添える。"""
    text = color.to_hex().upper()
    if color.alpha < 1:
        text += f"  ({round(max(0.0, color.alpha) * 100)}%)"
    return text


def describe_layer(page: SketchPage | None, layer: SketchLayer | None
                   ) -> tuple[dict[str, str], dict[str, Color | None]]:
    """プロパティ欄に表示する文字列 (キー -> 値) と、色見本に使う色を返す。

    座標は所属する画面の左上を原点とする (画面の外にある Layer は Page 座標)。
    """
    values = dict.fromkeys(FIELD_KEYS, "")
    colors: dict[str, Color | None] = dict.fromkeys(COLOR_KEYS)
    if layer is None:
        return values, colors

    values["name"] = layer.name
    values["type"] = layer.type
    placement = placement_of(page, layer) if page is not None else None
    if placement is not None:
        values["artboard"] = placement.artboard.name if placement.artboard else "(なし: Page 座標)"
        frame = placement.frame
        values["x"], values["y"] = format_number(frame.x), format_number(frame.y)
        values["width"], values["height"] = format_number(frame.width), format_number(frame.height)
        values["rotation"] = f"{format_number(placement.rotation)}°"
        style = placement.style
        colors["fill"] = style.fill
        colors["border"] = style.border.color if style.border else None
        if style.opacity < 1:
            values["type"] += f"  (opacity {round(style.opacity * 100)}%)"
    if isinstance(layer, TextLayer):
        colors["text_color"] = layer.color
        values["font"] = f"{layer.font_name}  {format_number(layer.font_size)}"

    for key, color in colors.items():
        if color is not None:
            values[key] = format_color(color)
        elif placement is not None and key != "text_color":
            values[key] = "なし"
    if placement is not None and placement.style.border is not None:
        values["border"] += f"  太さ {format_number(placement.style.border.thickness)}"
    return values, colors


class PropertiesPanel(ttk.LabelFrame):
    """プロパティ欄。値は読み取り専用の Entry に表示し、コピーできるようにする。"""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, text="プロパティ", padding=(6, 4))
        self.columnconfigure(2, weight=1)
        self._vars: dict[str, tk.StringVar] = {}
        self._swatches: dict[str, tk.Label] = {}  # 色見本
        for row, (label, fields) in enumerate(INFO_ROWS):
            self._build_row(row, label, fields)

    def _build_row(self, row: int, label: str, fields: list[tuple[str, str]]) -> None:
        # 列: 0 = 表示名、1 = 色見本、2 = 値
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", padx=(0, 6))
        values = ttk.Frame(self)
        values.grid(row=row, column=2, sticky="ew", pady=1)
        for key, caption in fields:
            if key in COLOR_KEYS:
                swatch = tk.Label(self, width=2, relief="solid", borderwidth=1)
                swatch.grid(row=row, column=1, sticky="w", padx=(0, 4))
                swatch.grid_remove()
                self._swatches[key] = swatch
            if caption:
                ttk.Label(values, text=caption).pack(side=tk.LEFT, padx=(0, 2))
            var = tk.StringVar()
            ttk.Entry(values, textvariable=var, state="readonly", width=8).pack(
                side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4 if caption else 0),
            )
            self._vars[key] = var

    def show(self, page: SketchPage | None, layer: SketchLayer | None) -> None:
        """Layer のプロパティを表示する。layer が None なら欄を空にする。"""
        values, colors = describe_layer(page, layer)
        for key, value in values.items():
            self._vars[key].set(value)
        for key, color in colors.items():
            swatch = self._swatches[key]
            if color is None:
                swatch.grid_remove()
            else:
                swatch.configure(background=color.to_hex())
                swatch.grid()
