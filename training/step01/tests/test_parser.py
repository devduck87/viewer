import json
import tempfile
import unittest
from pathlib import Path

from sketch_viewer.errors import MissingEntryError, PageNotFoundError, SketchFormatError
from sketch_viewer.parser import load_document, page_ref_to_path

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
        self.assertEqual(document.pages[0].id, "PAGE-0001")

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

    def test_pages_must_be_list(self) -> None:
        self._write("document.json", {"pages": {"_ref": "pages/X"}})
        with self.assertRaises(SketchFormatError):
            load_document(self.tmp)

    def _write(self, name: str, data: object) -> None:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")


class ParseHelpersTestCase(unittest.TestCase):
    def test_page_ref_to_path(self) -> None:
        self.assertEqual(page_ref_to_path({"_ref": "pages/ABC"}), "pages/ABC.json")
        self.assertEqual(page_ref_to_path({"_ref": "pages/ABC.json"}), "pages/ABC.json")


class ReferenceFilesTestCase(unittest.TestCase):
    """Sketch 公式 sketch-reference-files を使った確認。"""

    def test_all_reference_files_load(self) -> None:
        for directory in sorted(REFERENCE_DIR.iterdir()):
            with self.subTest(directory.name):
                self.assertGreaterEqual(len(load_document(directory).pages), 1)


if __name__ == "__main__":
    unittest.main()
