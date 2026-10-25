import tempfile
import unittest
from pathlib import Path

from sketch_viewer.errors import (
    InvalidJSONError,
    InvalidSketchFileError,
    MissingEntryError,
    SketchFileNotFoundError,
)
from sketch_viewer.reader import DirectorySketchReader, ZipSketchReader, open_reader

from . import SAMPLE_DIR, make_sketch_zip


class ReaderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.sketch_path = make_sketch_zip(SAMPLE_DIR, self.tmp / "basic.sketch")

    def test_open_reader_selects_implementation(self) -> None:
        with open_reader(SAMPLE_DIR) as reader:
            self.assertIsInstance(reader, DirectorySketchReader)
        with open_reader(self.sketch_path) as reader:
            self.assertIsInstance(reader, ZipSketchReader)

    def test_zip_and_directory_return_same_json(self) -> None:
        with open_reader(SAMPLE_DIR) as d, open_reader(self.sketch_path) as z:
            for name in ("document.json", "meta.json", "pages/PAGE-0001.json"):
                self.assertTrue(d.exists(name))
                self.assertTrue(z.exists(name))
                self.assertEqual(d.read_json(name), z.read_json(name))

    def test_missing_entry(self) -> None:
        for path in (SAMPLE_DIR, self.sketch_path):
            with open_reader(path) as reader:
                self.assertFalse(reader.exists("pages/NOPE.json"))
                with self.assertRaises(MissingEntryError):
                    reader.read_bytes("pages/NOPE.json")

    def test_directory_reader_rejects_paths_outside_root(self) -> None:
        with open_reader(SAMPLE_DIR / "pages") as reader:
            self.assertFalse(reader.exists("../document.json"))
            with self.assertRaises(MissingEntryError):
                reader.read_bytes("../document.json")

    def test_file_not_found(self) -> None:
        with self.assertRaises(SketchFileNotFoundError):
            open_reader(self.tmp / "missing.sketch")

    def test_not_a_zip(self) -> None:
        bogus = self.tmp / "bogus.sketch"
        bogus.write_text("not a zip", encoding="utf-8")
        with self.assertRaises(InvalidSketchFileError):
            open_reader(bogus)

    def test_invalid_json(self) -> None:
        (self.tmp / "document.json").write_text("{broken", encoding="utf-8")
        with open_reader(self.tmp) as reader:
            with self.assertRaises(InvalidJSONError):
                reader.read_json("document.json")


if __name__ == "__main__":
    unittest.main()
