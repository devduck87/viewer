import json
import tempfile
import unittest
from pathlib import Path

from sketch_viewer.errors import MissingEntryError, PageNotFoundError, SketchFormatError
from sketch_viewer.model import Frame
from sketch_viewer.parser import load_document, page_ref_to_path, parse_frame, parse_layer

from . import REFERENCE_DIR, SAMPLE_DIR, make_sketch_zip


class LoadDocumentTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def test_load_sample_directory(self) -> None:
        document = load_document(SAMPLE_DIR)
        self.assertEqual(document.id, "DOC-0001")
        self.assertEqual([p.name for p in document.pages], ["Page 1", "Page 2", "Page 3"])

        artboard = document.pages[0].layers[0]
        self.assertEqual((artboard.type, artboard.name), ("artboard", "Home"))
        header, content = artboard.children
        self.assertEqual([c.name for c in header.children], ["Background", "Title"])
        footer = content.children[3]
        self.assertEqual(footer.type, "group")
        self.assertEqual(footer.children[0].frame, Frame(240, 0, 120, 30))
        self.assertFalse(content.children[4].visible)
        self.assertEqual(document.warnings, [])

    def test_zip_matches_directory(self) -> None:
        sketch = make_sketch_zip(SAMPLE_DIR, self.tmp / "basic.sketch")
        self.assertEqual(load_document(sketch).pages, load_document(SAMPLE_DIR).pages)

    def test_missing_document_json(self) -> None:
        with self.assertRaises(MissingEntryError):
            load_document(self.tmp)

    def test_missing_page(self) -> None:
        self._write("document.json", {"pages": [{"_ref": "pages/GONE"}]})
        with self.assertRaises(PageNotFoundError):
            load_document(self.tmp)

    def test_invalid_page_reference(self) -> None:
        self._write("document.json", {"pages": ["pages/X"]})
        with self.assertRaises(SketchFormatError):
            load_document(self.tmp)

    def test_malformed_layers_are_skipped_with_warning(self) -> None:
        self._write("document.json", {"pages": [{"_ref": "pages/P"}]})
        self._write("pages/P.json", {
            "name": "P",
            "layers": [
                {"_class": "rectangle", "name": "ok", "frame": {"x": 1, "y": 2, "width": 3, "height": 4}},
                "garbage",
            ],
        })
        document = load_document(self.tmp)
        self.assertEqual([l.name for l in document.pages[0].layers], ["ok"])
        self.assertEqual(len(document.warnings), 1)

    def _write(self, name: str, data: object) -> None:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")


class ParseHelpersTestCase(unittest.TestCase):
    def test_page_ref_to_path(self) -> None:
        self.assertEqual(page_ref_to_path({"_ref": "pages/ABC"}), "pages/ABC.json")
        self.assertEqual(page_ref_to_path({"_ref": "pages/ABC.json"}), "pages/ABC.json")

    def test_unknown_layer_is_kept(self) -> None:
        layer = parse_layer({"_class": "somethingNew", "name": "X", "layers": [{"_class": "rectangle"}]})
        self.assertEqual(layer.type, "somethingNew")
        self.assertFalse(layer.is_supported)
        self.assertEqual(len(layer.children), 1)

    def test_missing_properties_use_defaults(self) -> None:
        layer = parse_layer({})
        self.assertEqual((layer.type, layer.name, layer.visible), ("unknown", "", True))
        self.assertEqual(layer.frame, Frame())

    def test_parse_frame_ignores_non_numeric(self) -> None:
        self.assertEqual(parse_frame({"x": "1", "y": True, "width": 10.5, "height": 2}), Frame(0, 0, 10.5, 2))


class ReferenceFilesTestCase(unittest.TestCase):
    """Sketch 公式 sketch-reference-files を使った確認。"""

    def test_all_reference_files_load(self) -> None:
        for directory in sorted(REFERENCE_DIR.iterdir()):
            with self.subTest(directory.name):
                document = load_document(directory)
                self.assertGreaterEqual(len(document.pages), 1)
                self.assertEqual(document.warnings, [])


if __name__ == "__main__":
    unittest.main()
