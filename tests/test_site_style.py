import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SiteStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.style = (ROOT / "site-style.css").read_text(encoding="utf-8")

    def test_override_stylesheet_loads_after_compiled_styles(self) -> None:
        contact = self.page.index('/contact-form.css?v=2')
        override = self.page.index('/site-style.css?v=1')
        script = self.page.index('/contact-form.js?v=3')
        self.assertLess(contact, override)
        self.assertLess(override, script)

    def test_instrument_visual_tokens_are_present(self) -> None:
        expected = (
            'IBM Plex Sans',
            '--bg: #edf1ef',
            '--text: #17211d',
            '--text-3: #5f6f66',
            '--azure: #087363',
            '--azure-deep: #245f87',
            '#b96700',
        )
        for token in expected:
            with self.subTest(token=token):
                self.assertIn(token, self.style)

    def test_generic_decorative_defaults_are_removed(self) -> None:
        self.assertRegex(
            self.style,
            re.compile(r"\.glow,\s*\.gridbg,\s*\.grain,\s*\.glyph\s*\{\s*display: none;", re.MULTILINE),
        )
        self.assertNotIn('gradient(', self.style)
        self.assertNotIn('border-radius: 999px', self.style)
        self.assertNotRegex(self.style, re.compile(r"letter-spacing:\s*-"))

    def test_layout_has_mobile_and_reduced_motion_rules(self) -> None:
        self.assertIn('@media (max-width: 900px)', self.style)
        self.assertIn('@media (max-width: 620px)', self.style)
        self.assertIn('@media (prefers-reduced-motion: reduce)', self.style)
        self.assertIn('.hero-grid > .canvas-wrap', self.style)


if __name__ == "__main__":
    unittest.main()
