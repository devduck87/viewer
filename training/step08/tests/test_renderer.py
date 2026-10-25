import unittest

from sketch_viewer.renderer import image_scale_factors, tk_font


class ImageScaleTestCase(unittest.TestCase):
    def test_factors(self) -> None:
        self.assertEqual(image_scale_factors(100, 100), (1, 1))
        self.assertEqual(image_scale_factors(100, 200), (2, 1))
        self.assertEqual(image_scale_factors(100, 50), (1, 2))
        self.assertEqual(image_scale_factors(80, 120), (3, 2))
        self.assertEqual(image_scale_factors(0, 10), (1, 1))

    def test_large_reduction(self) -> None:
        self.assertEqual(image_scale_factors(5000, 100), (1, 50))

    def test_intermediate_size_is_limited(self) -> None:
        zoom, _ = image_scale_factors(3000, 3001)
        self.assertLessEqual(3000 * zoom, 4096)


class TkFontTestCase(unittest.TestCase):
    def test_postscript_names(self) -> None:
        self.assertEqual(tk_font("Arial-BoldMT", 28), ("Arial", -28, "bold"))
        self.assertEqual(tk_font("TimesNewRomanPSMT", 16), ("Times New Roman", -16))
        self.assertEqual(tk_font("Helvetica-BoldOblique", 12.4), ("Helvetica", -12, "bold", "italic"))
        self.assertEqual(tk_font("Roboto-Regular", 50), ("Roboto", -50))
        self.assertEqual(tk_font("Recursive Beta 1.022", 50), ("Recursive Beta 1.022", -50))
        self.assertEqual(tk_font("", 0), ("TkDefaultFont", -1))


if __name__ == "__main__":
    unittest.main()
