import math
import unittest

from sketch_viewer.layout import bounds_of, layout_page
from sketch_viewer.model import Color, Frame
from sketch_viewer.parser import load_document
from sketch_viewer.renderer import shape_outline

from . import REFERENCE_DIR, SAMPLE_DIR


class LayoutTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.page = load_document(SAMPLE_DIR).pages[0]
        self.frames = {item.layer.name: item.frame for item in layout_page(self.page)}

    def test_child_is_offset_by_parents(self) -> None:
        # Home(0,0) > Content(20,100) > Footer(0,170) > Button(240,0)
        self.assertEqual(self.frames["Button"], Frame(260, 270, 120, 30))
        # Home(0,0) > Content(20,100) > Avatar(16,16)
        self.assertEqual(self.frames["Avatar"], Frame(36, 116, 48, 48))

    def test_hidden_layers_are_excluded(self) -> None:
        self.assertNotIn("Hidden Badge", self.frames)

    def test_parents_are_drawn_before_children(self) -> None:
        names = [item.layer.name for item in layout_page(self.page)]
        self.assertLess(names.index("Content"), names.index("Card"))
        self.assertLess(names.index("Card"), names.index("Avatar"))

    def test_bounds(self) -> None:
        self.assertEqual(bounds_of(layout_page(self.page)), Frame(0, 0, 580, 320))
        self.assertIsNone(bounds_of([]))


class ShapeGroupStyleTestCase(unittest.TestCase):
    def test_children_use_shape_group_style(self) -> None:
        page = load_document(REFERENCE_DIR / "groups").pages[0]
        items = {item.layer.name: item for item in layout_page(page)}
        self.assertEqual(items["Rectangle"].style.fill, Color(0, 1, 0, 1))
        self.assertEqual(items["Rectangle"].frame, Frame(0, 50, 50, 50))
        # Text は shapeGroup 外なので自身のスタイルのまま
        self.assertIsNone(items["Hello World"].style.fill)


class TransformLayoutTestCase(unittest.TestCase):
    def setUp(self) -> None:
        page = load_document(SAMPLE_DIR).pages[2]
        self.items = {item.layer.name: item for item in layout_page(page)}

    def test_rotated_frame_is_bounding_box(self) -> None:
        # 100x60 を 30 度回転した外接矩形
        frame = self.items["Rotated 30"].frame
        self.assertAlmostEqual(frame.width, 100 * math.cos(math.radians(30)) + 60 * math.sin(math.radians(30)))
        self.assertAlmostEqual(frame.x + frame.width / 2, 230)
        self.assertAlmostEqual(self.items["Rotated 30"].transform.angle, 30)

    def test_outline_follows_rotation(self) -> None:
        outline = self.items["Rotated 30"].outline()
        self.assertEqual(len(outline), 4)
        self.assertNotAlmostEqual(outline[0][1], outline[1][1])

    def test_symbol_instance_children_are_laid_out(self) -> None:
        names = [item.layer.name for item in layout_page(load_document(SAMPLE_DIR).pages[2])]
        # Master 1 つ + instance 2 つ分
        self.assertEqual(names.count("Label"), 3)

    def test_shape_outline(self) -> None:
        star = self.items["Star"].layer
        self.assertEqual(len(shape_outline(star)), 10)
        rounded = self.items["Rounded"].layer
        self.assertGreater(len(shape_outline(rounded)), 4)


if __name__ == "__main__":
    unittest.main()
