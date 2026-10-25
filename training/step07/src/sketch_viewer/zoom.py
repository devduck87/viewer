"""表示倍率の計算 (Tkinter 非依存)。"""

from __future__ import annotations

# 拡大・縮小で切り替える表示倍率
ZOOM_LEVELS = (0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)
MIN_ZOOM = ZOOM_LEVELS[0]
MAX_ZOOM = ZOOM_LEVELS[-1]


def clamp_zoom(zoom: float) -> float:
    """倍率を ZOOM_LEVELS の範囲に収める。"""
    return max(MIN_ZOOM, min(MAX_ZOOM, zoom))


def next_zoom_level(current: float, step: int) -> float:
    """current から step の向き (正: 拡大、負: 縮小) にある次の表示倍率を返す。

    current が一覧にない倍率 (全体表示の結果など) でも、その向きで最も近い倍率を返す。
    """
    if step > 0:
        return next((z for z in ZOOM_LEVELS if z > current * 1.001), MAX_ZOOM)
    return next((z for z in reversed(ZOOM_LEVELS) if z < current * 0.999), MIN_ZOOM)


def fit_zoom(content_width: float, content_height: float,
             view_width: float, view_height: float) -> float:
    """内容全体が表示領域に収まる倍率 (ZOOM_LEVELS の範囲内)。内容が空なら 1.0。"""
    ratios = [view / content
              for view, content in ((view_width, content_width), (view_height, content_height))
              if content > 0]
    if not ratios:
        return 1.0
    return clamp_zoom(min(ratios))


def format_zoom(zoom: float) -> str:
    """倍率を "125%" の形式にする。"""
    return f"{round(zoom * 100)}%"
