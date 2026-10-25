import unittest

from sketch_viewer.gui import (
    ZOOM_LEVELS,
    fit_zoom,
    format_color,
    format_number,
    format_zoom,
    next_zoom_level,
)
from sketch_viewer.model import Color


class FormatTestCase(unittest.TestCase):
    def test_format_number(self) -> None:
        self.assertEqual(format_number(12.0), "12")
        self.assertEqual(format_number(171.69872), "171.7")
        self.assertEqual(format_number(21.3333), "21.33")
        self.assertEqual(format_number(-0.001), "0")
        self.assertEqual(format_number(-30), "-30")

    def test_format_color(self) -> None:
        self.assertEqual(format_color(Color(1, 0, 0.5)), "#FF0080")
        self.assertEqual(format_color(Color(0, 0, 0, 0.5)), "#000000  (50%)")


class ZoomTestCase(unittest.TestCase):
    def test_next_zoom_level(self) -> None:
        self.assertEqual(next_zoom_level(1.0, 1), 1.25)
        self.assertEqual(next_zoom_level(1.0, -1), 0.75)
        # 一覧にない倍率 (全体表示の結果など) からは近い方へ
        self.assertEqual(next_zoom_level(0.8, 1), 1.0)
        self.assertEqual(next_zoom_level(0.8, -1), 0.75)
        self.assertEqual(next_zoom_level(ZOOM_LEVELS[-1], 1), ZOOM_LEVELS[-1])
        self.assertEqual(next_zoom_level(ZOOM_LEVELS[0], -1), ZOOM_LEVELS[0])

    def test_fit_zoom(self) -> None:
        self.assertEqual(fit_zoom(400, 200, 800, 800), 2.0)
        self.assertEqual(fit_zoom(400, 200, 200, 800), 0.5)
        self.assertEqual(fit_zoom(0, 100, 800, 50), 0.5)  # 幅 0 は高さだけで決める
        self.assertEqual(fit_zoom(0, 0, 800, 600), 1.0)
        self.assertEqual(fit_zoom(1, 1, 800, 600), ZOOM_LEVELS[-1])
        self.assertEqual(fit_zoom(100000, 100, 800, 600), ZOOM_LEVELS[0])

    def test_format_zoom(self) -> None:
        self.assertEqual(format_zoom(0.333), "33%")
        self.assertEqual(format_zoom(2), "200%")


if __name__ == "__main__":
    unittest.main()
