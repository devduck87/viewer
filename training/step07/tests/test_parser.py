import json
import tempfile
import unittest
from pathlib import Path

from sketch_viewer.errors import MissingEntryError, PageNotFoundError, SketchFormatError
from sketch_viewer.model import (
    BitmapLayer,
    Border,
    Color,
    Frame,
    ShapeLayer,
    SymbolInstanceLayer,
    TextLayer,
)
from sketch_viewer.parser import (
    load_document,
    page_ref_to_path,
    parse_frame,
    parse_layer,
    parse_page,
    parse_point,
    parse_style,
)

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

    def test_text_without_attributes_uses_defaults(self) -> None:
        text = parse_layer({"_class": "text", "attributedString": {"string": "Hi"}})
        self.assertIsInstance(text, TextLayer)
        self.assertEqual((text.text, text.font_size, text.color), ("Hi", 12.0, Color()))

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

    def test_parse_point(self) -> None:
        self.assertEqual(parse_point("{0.5, 1}"), (0.5, 1.0))
        self.assertEqual(parse_point("{-0.25, 1e-3}"), (-0.25, 0.001))
        self.assertIsNone(parse_point("0.5, 1"))
        self.assertIsNone(parse_point(None))

    def test_rotation_and_flip(self) -> None:
        layer = parse_layer({"_class": "group", "rotation": 30, "isFlippedHorizontal": True})
        self.assertEqual((layer.rotation, layer.flipped_horizontal, layer.flipped_vertical), (30, True, False))


class ShapeTestCase(unittest.TestCase):
    def test_points_and_corner_radius(self) -> None:
        shape = parse_layer({"_class": "rectangle", "points": [
            {"point": "{0, 0}", "cornerRadius": 8},
            {"point": "{1, 0}", "curveFrom": "{2, 2}", "hasCurveFrom": False},
            {"point": "{1, 1}", "curveTo": "{0.5, 1}", "hasCurveTo": True},
            {"point": "broken"},
        ]})
        self.assertIsInstance(shape, ShapeLayer)
        self.assertEqual(len(shape.points), 3)
        self.assertEqual(shape.points[0].corner_radius, 8)
        # hasCurveFrom が false なら制御点は頂点と同じ
        self.assertEqual(shape.points[1].curve_from, (1.0, 0.0))
        self.assertEqual(shape.points[2].curve_to, (0.5, 1.0))
        self.assertTrue(shape.is_closed)

    def test_fixed_radius_applies_to_all_points(self) -> None:
        shape = parse_layer({"_class": "rectangle", "fixedRadius": 5,
                             "points": [{"point": "{0, 0}"}, {"point": "{1, 0}"}, {"point": "{1, 1}"}]})
        self.assertEqual([p.corner_radius for p in shape.points], [5, 5, 5])

    def test_shape_without_points_uses_default(self) -> None:
        self.assertEqual(len(parse_layer({"_class": "rectangle"}).points), 4)
        self.assertEqual(len(parse_layer({"_class": "oval"}).points), 4)
        self.assertEqual(parse_layer({"_class": "shapePath"}).points, [])

    def test_open_path(self) -> None:
        path = load_document(REFERENCE_DIR / "shape-paths").pages[0].layers[0]
        self.assertEqual(path.type, "shapePath")
        self.assertFalse(path.is_closed)
        self.assertEqual(path.points[1].curve_from, (0.66666666666666652, 1.1666666666666665))


class BitmapTestCase(unittest.TestCase):
    def test_image_is_loaded(self) -> None:
        photo = load_document(SAMPLE_DIR).pages[1].layers[1]
        self.assertIsInstance(photo, BitmapLayer)
        self.assertEqual(photo.image_ref, "images/photo.png")
        self.assertTrue(photo.image_data.startswith(b"\x89PNG"))

    def test_image_is_loaded_from_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sketch = make_sketch_zip(SAMPLE_DIR, Path(tmp) / "basic.sketch")
            photo = load_document(sketch).pages[1].layers[1]
        self.assertTrue(photo.image_data.startswith(b"\x89PNG"))

    def test_missing_image_warns(self) -> None:
        document = load_document(REFERENCE_DIR / "images")
        self.assertIsNone(document.pages[0].layers[0].image_data)
        self.assertEqual(len(document.warnings), 1)

    def test_embedded_image(self) -> None:
        bitmap = parse_layer({"_class": "bitmap", "image": {"data": {"_data": "iVBORw0K"}}})
        self.assertEqual(bitmap.image_data, b"\x89PNG\r\n")


class SymbolTestCase(unittest.TestCase):
    def test_instance_is_expanded(self) -> None:
        master, instance = load_document(REFERENCE_DIR / "symbols").pages[0].layers
        self.assertIsInstance(instance, SymbolInstanceLayer)
        self.assertTrue(instance.resolved)
        self.assertEqual([c.name for c in instance.children], ["shape"])
        # Master の子とは別のオブジェクト
        self.assertIsNot(instance.children[0], master.children[0])
        self.assertEqual(instance.children[0].frame, master.children[0].frame)

    def test_string_override(self) -> None:
        master, instance = load_document(REFERENCE_DIR / "symbol-overrides").pages[0].layers
        self.assertEqual(master.children[0].text, "Label")
        self.assertEqual(instance.children[0].text, "Custom label")

    def test_foreign_symbol(self) -> None:
        instance = load_document(REFERENCE_DIR / "library-symbols").pages[0].layers[0]
        self.assertTrue(instance.resolved)
        self.assertEqual(instance.children[0].name, "my rect shape")

    def test_instance_resizes_children(self) -> None:
        # Master 100x32 -> instance 100x59.51171875
        document = load_document(REFERENCE_DIR / "smart-layout")
        instance = next(l for p in document.pages for l in p.layers if l.type == "symbolInstance")
        shape = instance.children[0]
        self.assertEqual(shape.children[0].frame.width, 100)
        self.assertAlmostEqual(shape.children[0].frame.height, 59.51171875)
        self.assertEqual(shape.children[1].text, "My really long text goes here")

    def test_missing_symbol_warns(self) -> None:
        warnings: list[str] = []
        page = parse_page({"layers": [{"_class": "symbolInstance", "name": "I", "symbolID": "X"}]}, warnings)
        self.assertFalse(page.layers[0].resolved)
        self.assertEqual(len(warnings), 1)

    def test_nested_symbol_overrides(self) -> None:
        def master(symbol_id, layers):
            return {"_class": "symbolMaster", "symbolID": symbol_id,
                    "frame": {"width": 100, "height": 100}, "layers": layers}

        def instance(oid, symbol_id, width=100, overrides=()):
            return {"_class": "symbolInstance", "do_objectID": oid, "symbolID": symbol_id,
                    "frame": {"width": width, "height": 100},
                    "overrideValues": [{"overrideName": k, "value": v} for k, v in overrides]}

        inner = master("INNER", [{"_class": "text", "do_objectID": "T",
                                  "attributedString": {"string": "inner"}}])
        outer = master("OUTER", [
            instance("N1", "INNER", overrides=[("T_stringValue", "from master")]),
            instance("N2", "INNER"),
        ])
        warnings: list[str] = []
        page = parse_page({"layers": [
            inner, outer, instance("I", "OUTER", width=200, overrides=[("N2/T_stringValue", "from instance")]),
        ]}, warnings)
        n1, n2 = page.layers[2].children
        self.assertEqual(n1.children[0].text, "from master")
        self.assertEqual(n2.children[0].text, "from instance")
        # 入れ子の instance にも外側の伸縮が反映される
        self.assertEqual(n1.frame.width, 200)
        self.assertEqual(warnings, [])

    def test_symbol_swap_to_none_hides(self) -> None:
        page = parse_page({"layers": [
            {"_class": "symbolMaster", "symbolID": "A", "layers": []},
            {"_class": "symbolMaster", "symbolID": "B", "layers": [
                {"_class": "symbolInstance", "do_objectID": "N", "symbolID": "A"},
            ]},
            {"_class": "symbolInstance", "symbolID": "B",
             "overrideValues": [{"overrideName": "N_symbolID", "value": ""}]},
        ]})
        self.assertFalse(page.layers[2].children[0].visible)

    def test_recursive_symbol_does_not_loop(self) -> None:
        warnings: list[str] = []
        parse_page({"layers": [
            {"_class": "symbolMaster", "symbolID": "A", "layers": [
                {"_class": "symbolInstance", "symbolID": "A"},
            ]},
        ]}, warnings)
        self.assertTrue(any("循環" in w for w in warnings))


class StyleTestCase(unittest.TestCase):
    def test_topmost_enabled_solid_fill_wins(self) -> None:
        style = parse_style({
            "fills": [
                {"isEnabled": True, "fillType": 0, "color": {"red": 1, "green": 0, "blue": 0, "alpha": 1}},
                {"isEnabled": True, "fillType": 0, "color": {"red": 0, "green": 1, "blue": 0, "alpha": 1}},
                {"isEnabled": False, "fillType": 0, "color": {"red": 0, "green": 0, "blue": 1, "alpha": 1}},
                {"isEnabled": True, "fillType": 1, "color": {"red": 1, "green": 1, "blue": 1, "alpha": 1}},
            ],
            "borders": [{"isEnabled": True, "thickness": 3, "color": {"red": 0, "green": 0, "blue": 0}}],
            "contextSettings": {"opacity": 0.5},
        })
        self.assertEqual(style.fill, Color(0, 1, 0, 1))
        self.assertEqual(style.border, Border(Color(0, 0, 0, 1), 3))
        self.assertEqual(style.opacity, 0.5)

    def test_missing_style(self) -> None:
        style = parse_style(None)
        self.assertIsNone(style.fill)
        self.assertIsNone(style.border)

    def test_artboard_background_color(self) -> None:
        red = {"red": 1, "green": 0, "blue": 0, "alpha": 1}
        with_bg = parse_layer({"_class": "artboard", "hasBackgroundColor": True, "backgroundColor": red})
        without_bg = parse_layer({"_class": "artboard", "hasBackgroundColor": False, "backgroundColor": red})
        self.assertEqual(with_bg.style.fill, Color(1, 0, 0, 1))
        self.assertIsNone(without_bg.style.fill)


class ReferenceFilesTestCase(unittest.TestCase):
    """Sketch 公式 sketch-reference-files を使った確認。"""

    def test_shape_group_fill_is_on_group(self) -> None:
        artboard = load_document(REFERENCE_DIR / "groups").pages[0].layers[0]
        text, shape = artboard.children[0].children
        self.assertEqual(shape.type, "shapeGroup")
        self.assertEqual(shape.style.fill, Color(0, 1, 0, 1))
        self.assertEqual(shape.children[0].type, "rectangle")

    def test_text(self) -> None:
        text = load_document(REFERENCE_DIR / "groups").pages[0].layers[0].children[0].children[0]
        self.assertIsInstance(text, TextLayer)
        self.assertEqual(text.text, "Hello World")
        self.assertEqual((text.font_name, text.font_size), ("Arial-BoldMT", 28))
        self.assertEqual(text.color, Color(1, 0, 0, 1))
        self.assertFalse(text.fixed_width)

    def test_fixed_width_text(self) -> None:
        headline, body = load_document(REFERENCE_DIR / "text").pages[0].layers
        self.assertFalse(headline.fixed_width)
        self.assertTrue(body.fixed_width)
        self.assertTrue(body.text.startswith("Lorem ipsum"))

    def test_all_reference_files_load(self) -> None:
        # images は公式リポジトリに画像ファイルが含まれないため警告が出る (BitmapTestCase で確認)
        for directory in sorted(REFERENCE_DIR.iterdir()):
            with self.subTest(directory.name):
                document = load_document(directory)
                self.assertGreaterEqual(len(document.pages), 1)
                if directory.name != "images":
                    self.assertEqual(document.warnings, [])
                self.assertEqual(document.unsupported_layer_counts(), {})


if __name__ == "__main__":
    unittest.main()
