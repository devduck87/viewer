import unittest

from sketch_viewer.renderer import tk_font


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
