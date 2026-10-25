import unittest

from sketch_viewer.model import Color
from sketch_viewer.parser import load_document
from sketch_viewer.properties import describe_layer, format_color, format_number

from . import SAMPLE_DIR


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


class DescribeLayerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.page = load_document(SAMPLE_DIR).pages[0]
        self.layers = {layer.name: layer for layer, _ in self.page.walk()}

    def test_nothing_selected(self) -> None:
        values, colors = describe_layer(self.page, None)
        self.assertTrue(all(value == "" for value in values.values()))
        self.assertTrue(all(color is None for color in colors.values()))

    def test_shape(self) -> None:
        values, colors = describe_layer(self.page, self.layers["Button"])
        self.assertEqual(values["artboard"], "Home")
        self.assertEqual((values["x"], values["y"], values["width"], values["height"]),
                         ("260", "270", "120", "30"))
        self.assertEqual(values["rotation"], "0°")
        self.assertEqual(colors["fill"], Color(0.2, 0.7, 0.4, 1))
        self.assertEqual(values["fill"], "#33B266")
        self.assertEqual(values["text_color"], "")

    def test_text(self) -> None:
        values, colors = describe_layer(self.page, self.layers["Title"])
        self.assertIsNotNone(colors["text_color"])
        self.assertNotEqual(values["font"], "")

    def test_outside_artboard(self) -> None:
        values, _ = describe_layer(self.page, self.layers["Loose Rectangle"])
        self.assertEqual(values["artboard"], "(なし: Page 座標)")


if __name__ == "__main__":
    unittest.main()
