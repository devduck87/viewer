"""Sketch データの内部モデル。

Parser が Sketch JSON をこのモデルへ変換し、GUI / Renderer はこのモデルだけを扱う。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterator

# ビューワーが描画に対応している Layer の種類 (Sketch の _class 値)
SUPPORTED_LAYER_TYPES = frozenset({
    "group", "artboard", "symbolMaster",
    "rectangle", "oval", "text",
    "shapeGroup", "shapePath", "triangle", "star", "polygon",
    "bitmap", "symbolInstance", "slice",
})
# 1 つの画面を表す Layer (Page 直下に置かれ、子 Layer の座標の基準となる)
ARTBOARD_LAYER_TYPES = frozenset({"artboard", "symbolMaster"})
# points (頂点列) で形状を表す Layer
SHAPE_LAYER_TYPES = frozenset({"rectangle", "oval", "shapePath", "triangle", "star", "polygon"})


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


@dataclass(frozen=True)
class Color:
    """RGBA カラー。各成分は 0.0 - 1.0。"""

    red: float = 0.0
    green: float = 0.0
    blue: float = 0.0
    alpha: float = 1.0

    def to_hex(self) -> str:
        """``#rrggbb`` 形式に変換する (alpha は含まない)。"""
        components = (self.red, self.green, self.blue)
        return "#" + "".join(f"{round(_clamp01(c) * 255):02x}" for c in components)


@dataclass(frozen=True)
class Border:
    color: Color
    thickness: float = 1.0


@dataclass(frozen=True)
class Style:
    """Layer の見た目。fill / border は最前面の有効な単色だけを保持する。"""

    fill: Color | None = None
    border: Border | None = None
    opacity: float = 1.0


@dataclass(frozen=True)
class CurvePoint:
    """パスの頂点。座標は Layer の frame に対する正規化値 (0.0 - 1.0)。"""

    point: tuple[float, float]
    curve_from: tuple[float, float]  # 次の頂点へ向かう曲線の制御点
    curve_to: tuple[float, float]  # 前の頂点から来る曲線の制御点
    corner_radius: float = 0.0


@dataclass
class SketchLayer:
    """すべての Layer に共通する情報。種類固有の情報はサブクラスが持つ。"""

    id: str
    name: str
    type: str  # Sketch の _class 値 ("group", "rectangle" など)
    frame: Frame
    visible: bool = True
    children: list[SketchLayer] = field(default_factory=list)
    style: Style = field(default_factory=Style)
    # frame の中心を基準とした回転 (度、反時計回り) と反転
    rotation: float = 0.0
    flipped_horizontal: bool = False
    flipped_vertical: bool = False

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

    def matches(self, query: str) -> bool:
        """名前に query を含むか (大文字・小文字を区別しない)。空の query には一致しない。"""
        needle = query.casefold()
        return bool(needle) and needle in self.name.casefold()


@dataclass
class TextLayer(SketchLayer):
    """Text Layer。書式は先頭の文字の属性だけを保持する。"""

    text: str = ""
    font_name: str = ""  # PostScript 名 (例: "Arial-BoldMT")
    font_size: float = 12.0
    color: Color = field(default_factory=Color)
    alignment: str = "left"  # "left" / "right" / "center" / "justified"
    fixed_width: bool = False  # True なら frame の幅で折り返す

    def matches(self, query: str) -> bool:
        """名前に加えて、表示している文字列も検索対象にする。"""
        needle = query.casefold()
        return super().matches(query) or (bool(needle) and needle in self.text.casefold())


@dataclass
class ShapeLayer(SketchLayer):
    """rectangle / oval / shapePath / star などの図形 Layer。"""

    points: list[CurvePoint] = field(default_factory=list)
    is_closed: bool = True
    # 古い形式の角丸 (各頂点の cornerRadius がすべて 0 のときに使う)
    fixed_radius: float = 0.0


@dataclass
class BitmapLayer(SketchLayer):
    """画像 Layer。image_data は画像を読み込めなかった場合 None。"""

    image_ref: str = ""
    image_data: bytes | None = None


@dataclass
class SymbolInstanceLayer(SketchLayer):
    """Symbol Instance (Symbol Master の複製)。

    読み込みの最後に、参照先 Master の子 Layer を複製して children に展開する
    (symbols.py)。参照先が見つからなければ resolved は False のまま。
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

    def artboards(self) -> list[SketchLayer]:
        """Page 直下の画面 (Artboard / Symbol Master) を並び順に返す。"""
        return [layer for layer in self.layers if layer.is_artboard]


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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
