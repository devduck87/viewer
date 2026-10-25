"""座標変換と図形の輪郭計算。

Tkinter Canvas は曲線・回転を直接扱えないため、図形はすべて折れ線 (頂点列) に近似し、
アフィン変換で Page 座標へ写して描画する。Tkinter には依存しない。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .model import CurvePoint, Frame, SketchLayer

Point = tuple[float, float]

# 円弧を 3 次ベジェで近似するときの係数 (90 度の円弧で誤差最小)
_KAPPA = 0.5522847498
# 曲線 1 区間あたりの分割数
_CURVE_STEPS = 16
_EPSILON = 1e-9


@dataclass(frozen=True)
class Affine:
    """2 次元アフィン変換。``x' = a*x + c*y + e``、``y' = b*x + d*y + f``。"""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    @classmethod
    def translation(cls, dx: float, dy: float) -> Affine:
        return cls(e=dx, f=dy)

    @classmethod
    def scaling(cls, sx: float, sy: float) -> Affine:
        return cls(a=sx, d=sy)

    @classmethod
    def rotation(cls, degrees: float) -> Affine:
        """y 軸下向きの座標系で、画面上 時計回りに ``degrees`` 度回転する。"""
        rad = math.radians(degrees)
        cos, sin = math.cos(rad), math.sin(rad)
        return cls(a=cos, b=sin, c=-sin, d=cos)

    def __matmul__(self, other: Affine) -> Affine:
        """合成変換 (``other`` を先に適用する)。"""
        return Affine(
            a=self.a * other.a + self.c * other.b,
            b=self.b * other.a + self.d * other.b,
            c=self.a * other.c + self.c * other.d,
            d=self.b * other.c + self.d * other.d,
            e=self.a * other.e + self.c * other.f + self.e,
            f=self.b * other.e + self.d * other.f + self.f,
        )

    def apply(self, x: float, y: float) -> Point:
        return self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f

    @property
    def angle(self) -> float:
        """x 軸の向きから求めた画面上の回転角 (度、反時計回り)。"""
        return math.degrees(math.atan2(-self.b, self.a))


def layer_transform(layer: SketchLayer) -> Affine:
    """Layer のローカル座標 (frame 左上が原点) を親 Layer の座標へ写す変換。

    Sketch の回転・反転は frame の中心を基準とし、rotation は反時計回りが正。
    """
    frame = layer.frame
    transform = Affine.translation(frame.x, frame.y)
    if layer.rotation or layer.flipped_horizontal or layer.flipped_vertical:
        cx, cy = frame.width / 2, frame.height / 2
        transform = (
            transform
            @ Affine.translation(cx, cy)
            @ Affine.rotation(-layer.rotation)
            @ Affine.scaling(-1 if layer.flipped_horizontal else 1, -1 if layer.flipped_vertical else 1)
            @ Affine.translation(-cx, -cy)
        )
    return transform


def rect_points(width: float, height: float) -> list[Point]:
    return [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]


def bounding_frame(points: list[Point]) -> Frame:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return Frame(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def contains_point(polygon: list[Point], x: float, y: float) -> bool:
    """点 (x, y) が多角形の内側 (境界を含む) にあるか。"""
    inside = False
    n = len(polygon)
    for i in range(n):
        p, q = polygon[i], polygon[(i + 1) % n]
        if _on_segment(p, q, (x, y)):
            return True
        if (p[1] > y) != (q[1] > y) and x < p[0] + (y - p[1]) * (q[0] - p[0]) / (q[1] - p[1]):
            inside = not inside
    return inside


def default_points(shape_type: str, corner_radius: float = 0.0) -> list[CurvePoint]:
    """points を持たない古い形式の rectangle / oval 用の頂点列。"""
    if shape_type == "oval":
        k = _KAPPA / 2
        return [
            CurvePoint((0.5, 0.0), (0.5 + k, 0.0), (0.5 - k, 0.0)),
            CurvePoint((1.0, 0.5), (1.0, 0.5 + k), (1.0, 0.5 - k)),
            CurvePoint((0.5, 1.0), (0.5 - k, 1.0), (0.5 + k, 1.0)),
            CurvePoint((0.0, 0.5), (0.0, 0.5 - k), (0.0, 0.5 + k)),
        ]
    return [CurvePoint(p, p, p, corner_radius) for p in ((0, 0), (1, 0), (1, 1), (0, 1))]


def flatten_path(points: list[CurvePoint], width: float, height: float,
                 closed: bool = True) -> list[Point]:
    """Sketch の頂点列を frame の大きさに合わせ、折れ線に近似したローカル座標を返す。

    ベジェ曲線は分割して近似し、直線同士の角にある cornerRadius は円弧で丸める。
    """
    n = len(points)
    if n == 0:
        return []

    def scale(p: tuple[float, float]) -> Point:
        return p[0] * width, p[1] * height

    anchors = [scale(p.point) for p in points]
    controls_from = [scale(p.curve_from) for p in points]
    controls_to = [scale(p.curve_to) for p in points]
    segment_count = n if closed else n - 1

    def is_straight(i: int) -> bool:
        j = (i + 1) % n
        return _close(controls_from[i], anchors[i]) and _close(controls_to[j], anchors[j])

    result: list[Point] = []
    for i in range(n):
        has_prev = closed or i > 0
        has_next = closed or i < n - 1
        rounded = None
        if points[i].corner_radius > 0 and has_prev and has_next \
                and is_straight((i - 1) % n) and is_straight(i):
            rounded = _round_corner(anchors[(i - 1) % n], anchors[i], anchors[(i + 1) % n],
                                    points[i].corner_radius)
        result.extend(rounded or [anchors[i]])

        if i < segment_count and not is_straight(i):
            j = (i + 1) % n
            result.extend(_bezier(anchors[i], controls_from[i], controls_to[j], anchors[j])[1:-1])
    return result


def _round_corner(prev: Point, corner: Point, next_: Point, radius: float) -> list[Point] | None:
    """corner の角を半径 radius で丸めた点列。丸められなければ None。"""
    ux, uy = prev[0] - corner[0], prev[1] - corner[1]
    vx, vy = next_[0] - corner[0], next_[1] - corner[1]
    len_u, len_v = math.hypot(ux, uy), math.hypot(vx, vy)
    if len_u < _EPSILON or len_v < _EPSILON:
        return None
    cos_theta = max(-1.0, min(1.0, (ux * vx + uy * vy) / (len_u * len_v)))
    theta = math.acos(cos_theta)
    if theta < 1e-3 or math.pi - theta < 1e-3:
        return None
    # 角から接点までの距離。辺の半分を超えないよう制限する (Sketch と同じ挙動)
    tangent = min(radius / math.tan(theta / 2), len_u / 2, len_v / 2)
    start = (corner[0] + ux / len_u * tangent, corner[1] + uy / len_u * tangent)
    end = (corner[0] + vx / len_v * tangent, corner[1] + vy / len_v * tangent)
    c1 = (start[0] + (corner[0] - start[0]) * _KAPPA, start[1] + (corner[1] - start[1]) * _KAPPA)
    c2 = (end[0] + (corner[0] - end[0]) * _KAPPA, end[1] + (corner[1] - end[1]) * _KAPPA)
    return _bezier(start, c1, c2, end)


def _bezier(p0: Point, p1: Point, p2: Point, p3: Point, steps: int = _CURVE_STEPS) -> list[Point]:
    """3 次ベジェ曲線を steps 分割した点列 (両端を含む)。"""
    result = []
    for k in range(steps + 1):
        t = k / steps
        mt = 1 - t
        w0, w1, w2, w3 = mt ** 3, 3 * mt * mt * t, 3 * mt * t * t, t ** 3
        result.append((
            w0 * p0[0] + w1 * p1[0] + w2 * p2[0] + w3 * p3[0],
            w0 * p0[1] + w1 * p1[1] + w2 * p2[1] + w3 * p3[1],
        ))
    return result


def _on_segment(p: Point, q: Point, r: Point) -> bool:
    cross = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (abs(cross) < 1e-6
            and min(p[0], q[0]) - _EPSILON <= r[0] <= max(p[0], q[0]) + _EPSILON
            and min(p[1], q[1]) - _EPSILON <= r[1] <= max(p[1], q[1]) + _EPSILON)


def _close(p: Point, q: Point) -> bool:
    return abs(p[0] - q[0]) < _EPSILON and abs(p[1] - q[1]) < _EPSILON
