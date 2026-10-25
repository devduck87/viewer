import math
import unittest

from sketch_viewer.layout import bounds_of, layout_page, placement_of, show_all
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


class VisibilityAndRootsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.page = load_document(SAMPLE_DIR).pages[0]
        self.layers = {layer.name: layer for layer, _ in self.page.walk()}

    def names(self, items) -> list[str]:
        return [item.layer.name for item in items]

    def test_show_all_includes_hidden_layers(self) -> None:
        self.assertIn("Hidden Badge", self.names(layout_page(self.page, show_all)))

    def test_is_visible_excludes_descendants(self) -> None:
        content = self.layers["Content"]
        names = self.names(layout_page(self.page, lambda layer: layer is not content))
        self.assertNotIn("Content", names)
        self.assertNotIn("Button", names)
        self.assertIn("Title", names)

    def test_roots_limits_to_artboard(self) -> None:
        items = layout_page(self.page, roots=[self.layers["Home"]])
        names = self.names(items)
        self.assertIn("Button", names)
        self.assertNotIn("Loose Rectangle", names)
        self.assertTrue(all(item.root is self.layers["Home"] for item in items))
        self.assertEqual(bounds_of(items), Frame(0, 0, 400, 320))


class PlacementTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.pages = load_document(SAMPLE_DIR).pages

    def placement(self, page_index: int, name: str, nth: int = 0):
        page = self.pages[page_index]
        layer = [layer for layer, _ in page.walk() if layer.name == name][nth]
        return placement_of(page, layer)

    def test_relative_to_artboard(self) -> None:
        placement = self.placement(0, "Button")
        self.assertEqual(placement.artboard.name, "Home")
        self.assertEqual(placement.frame, Frame(260, 270, 120, 30))
        self.assertEqual(placement.style.fill, Color(0.2, 0.7, 0.4, 1))

    def test_each_artboard_is_its_own_origin(self) -> None:
        # Badge (symbolMaster) は Page 上 (0, 260) にあるが、子は Badge の左上が原点
        placement = self.placement(2, "Label")
        self.assertEqual(placement.artboard.name, "Badge")
        self.assertEqual(placement.frame, Frame(16, 11, 88, 18))

    def test_outside_artboard_uses_page_coordinates(self) -> None:
        placement = self.placement(0, "Loose Rectangle")
        self.assertIsNone(placement.artboard)
        self.assertEqual(placement.frame, Frame(460, 40, 120, 80))
        # Symbol Instance の子も画面外なら Page 座標
        self.assertEqual(self.placement(2, "Label", 1).frame, Frame(176, 271, 88, 18))

    def test_rotated_frame_is_unrotated(self) -> None:
        placement = self.placement(2, "Rotated 30")
        self.assertAlmostEqual(placement.frame.x, 180)
        self.assertAlmostEqual(placement.frame.y, 30)
        self.assertEqual((placement.frame.width, placement.frame.height), (100, 60))
        self.assertAlmostEqual(placement.rotation, 30)

    def test_hidden_layer_and_unknown_layer(self) -> None:
        self.assertEqual(self.placement(0, "Hidden Badge").frame, Frame(320, 110, 40, 20))
        self.assertIsNone(placement_of(self.pages[1], self.pages[0].layers[0]))


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
