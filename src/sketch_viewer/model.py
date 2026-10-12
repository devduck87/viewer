"""Sketch データの内部モデル。

GUI / Renderer は Sketch JSON を直接参照せず、このモデルだけを扱う。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterator

# 現在のビューワーが描画に対応している Layer の種類 (Sketch の _class 値)
SUPPORTED_LAYER_TYPES = frozenset({
    "group", "artboard", "symbolMaster", "symbolInstance", "shapeGroup",
    "rectangle", "oval", "shapePath", "triangle", "star", "polygon",
    "text", "bitmap", "slice",
})
# points (曲線の頂点列) で形状を表す Layer
SHAPE_LAYER_TYPES = frozenset({"rectangle", "oval", "shapePath", "triangle", "star", "polygon"})


@dataclass(frozen=True)
class Color:
    """RGBA カラー。各成分は 0.0 - 1.0。"""

    red: float = 0.0
    green: float = 0.0
    blue: float = 0.0
    alpha: float = 1.0

    def to_hex(self) -> str:
        """``#rrggbb`` 形式に変換する (alpha は含まない)。"""
        return "#" + "".join(
            f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in (self.red, self.green, self.blue)
        )


@dataclass(frozen=True)
class Border:
    color: Color
    thickness: float = 1.0


@dataclass(frozen=True)
class Style:
    """Layer の見た目。fill / border は最前面の有効な単色のみを保持する。"""

    fill: Color | None = None
    border: Border | None = None
    opacity: float = 1.0


@dataclass(frozen=True)
class Frame:
    """Layer の位置とサイズ。座標は親 Layer からの相対値。"""

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
        return Frame(self.x + dx, self.y + dy, self.width, self.height)


@dataclass(frozen=True)
class CurvePoint:
    """パスの頂点。座標は Layer の frame に対する正規化値 (0.0 - 1.0)。"""

    point: tuple[float, float]
    curve_from: tuple[float, float]  # 次の頂点へ向かう制御点
    curve_to: tuple[float, float]  # 前の頂点から来る制御点
    corner_radius: float = 0.0


@dataclass
class SketchLayer:
    id: str
    name: str
    type: str
    frame: Frame
    visible: bool = True
    style: Style = field(default_factory=Style)
    children: list[SketchLayer] = field(default_factory=list)
    # frame 中心を基準とした回転 (度、反時計回り) と反転
    rotation: float = 0.0
    flipped_horizontal: bool = False
    flipped_vertical: bool = False

    @property
    def is_supported(self) -> bool:
        return self.type in SUPPORTED_LAYER_TYPES

    def walk(self, depth: int = 0) -> Iterator[tuple[SketchLayer, int]]:
        """自身と子孫を深さ優先で (layer, depth) として列挙する。"""
        yield self, depth
        for child in self.children:
            yield from child.walk(depth + 1)


@dataclass
class TextLayer(SketchLayer):
    """Text Layer。書式は先頭の文字属性のみを保持する。"""

    text: str = ""
    font_name: str = ""
    font_size: float = 12.0
    color: Color = field(default_factory=Color)
    alignment: str = "left"  # "left" / "right" / "center" / "justified"
    # True: frame の幅で折り返す (Sketch の固定幅テキスト)
    fixed_width: bool = False


@dataclass
class ShapeLayer(SketchLayer):
    """rectangle / oval / shapePath / star などの図形 Layer。"""

    points: list[CurvePoint] = field(default_factory=list)
    is_closed: bool = True
    # 旧形式の角丸 (各頂点の cornerRadius がすべて 0 のときに使う)
    fixed_radius: float = 0.0


@dataclass
class BitmapLayer(SketchLayer):
    """画像 Layer。image_data は読み込めなかった場合 None。"""

    image_ref: str = ""
    image_data: bytes | None = None


@dataclass
class SymbolInstanceLayer(SketchLayer):
    """Symbol Instance。

    読み込み時に参照先 Symbol Master の子 Layer を複製して children に展開する
    (Override 適用・instance の大きさへの伸縮済み)。参照先が見つからなければ resolved = False。
    """

    symbol_id: str = ""
    resolved: bool = False
    # Override の値。キーは "<Layer ID のパス>_<プロパティ名>" (例: "ABC/DEF_stringValue")
    overrides: dict[str, object] = field(default_factory=dict, repr=False)


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
    source: str = ""
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
    blocks: list[str] = []
    for page in document.pages:
        lines = [f"Page: {page.name}", ""]
        for layer, depth in page.walk():
            marks = []
            if not layer.visible:
                marks.append("hidden")
            if not layer.is_supported:
                marks.append("unsupported")
            suffix = f"  [{', '.join(marks)}]" if marks else ""
            lines.append(f"{indent * depth}{layer.type}: {layer.name}{suffix}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
