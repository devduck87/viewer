import unittest

from sketch_viewer.layout import bounds_of, layout_page
from sketch_viewer.model import Frame
from sketch_viewer.parser import load_document

from . import SAMPLE_DIR


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


if __name__ == "__main__":
    unittest.main()
