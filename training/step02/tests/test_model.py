import unittest

from sketch_viewer.model import (
    Frame,
    SketchDocument,
    SketchLayer,
    SketchPage,
    format_tree,
)


def layer(name: str, type_: str = "group", children=None, visible=True) -> SketchLayer:
    return SketchLayer(id=name, name=name, type=type_, frame=Frame(), visible=visible,
                       children=children or [])


class ModelTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.page = SketchPage(id="p", name="Page 1", layers=[
            layer("Header", "group", [layer("Background"), layer("Title", "hotspot")]),
            layer("Hidden", visible=False),
        ])
        self.document = SketchDocument(id="d", pages=[self.page])

    def test_frame(self) -> None:
        frame = Frame(10, 20, 30, 40)
        self.assertEqual((frame.right, frame.bottom), (40, 60))
        self.assertEqual(frame.offset(5, -5), Frame(15, 15, 30, 40))

    def test_walk_is_depth_first(self) -> None:
        self.assertEqual(
            [(l.name, d) for l, d in self.page.walk()],
            [("Header", 0), ("Background", 1), ("Title", 1), ("Hidden", 0)],
        )

    def test_unsupported_counts(self) -> None:
        self.assertEqual(self.document.unsupported_layer_counts(), {"hotspot": 1})

    def test_format_tree(self) -> None:
        self.assertEqual(format_tree(self.document), "\n".join([
            "Page: Page 1",
            "",
            "group: Header",
            "  group: Background",
            "  hotspot: Title  [unsupported]",
            "group: Hidden  [hidden]",
        ]))


if __name__ == "__main__":
    unittest.main()
