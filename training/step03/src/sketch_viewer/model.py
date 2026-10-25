"""Sketch データの内部モデル。

Parser が Sketch JSON をこのモデルへ変換し、GUI はこのモデルだけを扱う。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterator

# ビューワーが描画に対応している Layer の種類 (Sketch の _class 値)
SUPPORTED_LAYER_TYPES = frozenset({
    "group", "artboard", "symbolMaster",
})
# 1 つの画面を表す Layer (Page 直下に置かれ、子 Layer の座標の基準となる)
ARTBOARD_LAYER_TYPES = frozenset({"artboard", "symbolMaster"})


@dataclass(frozen=True)
class Frame:
    """Layer の位置とサイズ。座標は親 Layer の左上を原点とした相対値。"""

    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def offset(self, dx: float, dy: float) -> Frame:
        """(dx, dy) だけ平行移動した Frame を返す。"""
        return Frame(self.x + dx, self.y + dy, self.width, self.height)


@dataclass
class SketchLayer:
    """すべての Layer に共通する情報。種類固有の情報はサブクラスが持つ。"""

    id: str
    name: str
    type: str  # Sketch の _class 値 ("group", "rectangle" など)
    frame: Frame
    visible: bool = True
    children: list[SketchLayer] = field(default_factory=list)

    @property
    def is_supported(self) -> bool:
        return self.type in SUPPORTED_LAYER_TYPES

    @property
    def is_artboard(self) -> bool:
        return self.type in ARTBOARD_LAYER_TYPES

    def walk(self, depth: int = 0) -> Iterator[tuple[SketchLayer, int]]:
        """自身と子孫を深さ優先で (layer, depth) として列挙する。"""
        yield self, depth
        for child in self.children:
            yield from child.walk(depth + 1)


@dataclass
class SketchPage:
    id: str
    name: str
    layers: list[SketchLayer] = field(default_factory=list)

    def walk(self) -> Iterator[tuple[SketchLayer, int]]:
        """Page 内の全 Layer を深さ優先で (layer, depth) として列挙する。"""
        for layer in self.layers:
            yield from layer.walk()


@dataclass
class SketchDocument:
    id: str
    pages: list[SketchPage] = field(default_factory=list)
    source: str = ""  # 読み込んだファイルのパス
    # 致命的ではない解析上の問題 (不正な Layer データなど)
    warnings: list[str] = field(default_factory=list)

    def unsupported_layer_counts(self) -> Counter[str]:
        """未対応 Layer の種類ごとの件数を返す。"""
        return Counter(
            layer.type
            for page in self.pages
            for layer, _ in page.walk()
            if not layer.is_supported
        )


def format_tree(document: SketchDocument, indent: str = "  ") -> str:
    """Document の Page / Layer 階層をコンソール表示用の文字列にする。"""
    blocks = []
    for page in document.pages:
        lines = [f"Page: {page.name}", ""]
        for layer, depth in page.walk():
            lines.append(f"{indent * depth}{layer.type}: {layer.name}{_tree_marks(layer)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _tree_marks(layer: SketchLayer) -> str:
    """format_tree で Layer 名の後ろに付ける印 (例: "  [hidden, unsupported]")。"""
    marks = []
    if not layer.visible:
        marks.append("hidden")
    if not layer.is_supported:
        marks.append("unsupported")
    return f"  [{', '.join(marks)}]" if marks else ""
