import math
import unittest

from sketch_viewer.geometry import Affine, contains_point, default_points, flatten_path, layer_transform
from sketch_viewer.model import CurvePoint, Frame, SketchLayer


def point(x, y, radius=0.0):
    return CurvePoint((x, y), (x, y), (x, y), radius)


def assert_points_almost_equal(test, actual, expected):
    test.assertEqual(len(actual), len(expected))
    for (ax, ay), (ex, ey) in zip(actual, expected):
        test.assertAlmostEqual(ax, ex)
        test.assertAlmostEqual(ay, ey)


class AffineTestCase(unittest.TestCase):
    def test_compose_applies_right_first(self) -> None:
        transform = Affine.translation(10, 0) @ Affine.scaling(2, 3)
        self.assertEqual(transform.apply(1, 1), (12, 3))

    def test_rotation_is_clockwise_on_screen(self) -> None:
        x, y = Affine.rotation(90).apply(1, 0)
        self.assertAlmostEqual(x, 0)
        self.assertAlmostEqual(y, 1)
        self.assertAlmostEqual(Affine.rotation(-30).angle, 30)


class LayerTransformTestCase(unittest.TestCase):
    def layer(self, **kwargs) -> SketchLayer:
        return SketchLayer(id="", name="", type="rectangle", frame=Frame(10, 20, 100, 50), **kwargs)

    def test_translation_only(self) -> None:
        self.assertEqual(layer_transform(self.layer()), Affine.translation(10, 20))

    def test_rotation_is_around_center(self) -> None:
        transform = layer_transform(self.layer(rotation=90))
        # 中心は動かない
        assert_points_almost_equal(self, [transform.apply(50, 25)], [(60, 45)])
        # 反時計回り 90 度: 右上の角は右上 -> 中心の上側へ
        assert_points_almost_equal(self, [transform.apply(100, 0)], [(35, -5)])
        self.assertAlmostEqual(transform.angle, 90)

    def test_flip(self) -> None:
        transform = layer_transform(self.layer(flipped_horizontal=True))
        assert_points_almost_equal(self, [transform.apply(0, 0)], [(110, 20)])
        transform = layer_transform(self.layer(flipped_vertical=True))
        assert_points_almost_equal(self, [transform.apply(0, 0)], [(10, 70)])


class FlattenPathTestCase(unittest.TestCase):
    def test_straight_rectangle(self) -> None:
        points = [point(0, 0), point(1, 0), point(1, 1), point(0, 1)]
        self.assertEqual(flatten_path(points, 100, 50), [(0, 0), (100, 0), (100, 50), (0, 50)])

    def test_rounded_corner_stays_inside(self) -> None:
        points = [point(0, 0, 10), point(1, 0), point(1, 1), point(0, 1)]
        result = flatten_path(points, 100, 50)
        # 角 (0, 0) は通らず、接点 (0, 10) と (10, 0) を通る
        self.assertNotIn((0.0, 0.0), result)
        assert_points_almost_equal(self, [result[0], result[16]], [(0, 10), (10, 0)])
        # 円弧の中点は半径 10 の円上
        mx, my = result[8]
        self.assertAlmostEqual(math.hypot(mx - 10, my - 10), 10, delta=0.05)

    def test_corner_radius_is_clamped_to_half_edge(self) -> None:
        points = [point(0, 0, 100), point(1, 0), point(1, 1), point(0, 1)]
        result = flatten_path(points, 40, 20)
        assert_points_almost_equal(self, [result[0], result[16]], [(0, 10), (10, 0)])

    def test_curve_is_sampled(self) -> None:
        points = [CurvePoint((0, 0), (0, 1), (0, 0)), CurvePoint((1, 0), (1, 0), (1, 1))]
        result = flatten_path(points, 10, 10, closed=False)
        self.assertEqual(result[0], (0, 0))
        self.assertEqual(result[-1], (10, 0))
        # 制御点 (0, 10), (10, 10) の曲線は中点で y = 7.5
        assert_points_almost_equal(self, [result[8]], [(5, 7.5)])

    def test_open_path_has_no_closing_segment(self) -> None:
        points = [point(0, 0, 5), point(1, 0), point(1, 1, 5)]
        # 開いたパスの端点は丸めない
        self.assertEqual(flatten_path(points, 10, 10, closed=False)[0], (0, 0))

    def test_default_oval(self) -> None:
        result = flatten_path(default_points("oval"), 100, 100)
        for x, y in result:
            self.assertAlmostEqual(math.hypot(x - 50, y - 50), 50, delta=0.05)

    def test_empty(self) -> None:
        self.assertEqual(flatten_path([], 10, 10), [])


class ContainsPointTestCase(unittest.TestCase):
    def test_rectangle(self) -> None:
        rect = [(0, 0), (10, 0), (10, 10), (0, 10)]
        self.assertTrue(contains_point(rect, 5, 5))
        self.assertTrue(contains_point(rect, 10, 5))  # 境界
        self.assertTrue(contains_point(rect, 0, 0))  # 頂点
        self.assertFalse(contains_point(rect, 11, 5))
        self.assertFalse(contains_point(rect, 5, -1))

    def test_rotated_square(self) -> None:
        diamond = [(5, 0), (10, 5), (5, 10), (0, 5)]
        self.assertTrue(contains_point(diamond, 5, 5))
        self.assertFalse(contains_point(diamond, 1, 1))


if __name__ == "__main__":
    unittest.main()
