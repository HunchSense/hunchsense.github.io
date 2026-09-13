import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SiteCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_product_claims_are_preserved(self) -> None:
        expected = (
            "Project Sense",
            "open-source visual programming",
            "built-in AI",
            "microsecond performance",
            "no vendor lock-in",
            "LabVIEW",
            "NI hardware",
            "MATLAB",
            "Python",
            "import VIs",
            "C++/Rust hardware engine",
            "No request caps",
            "Open-source core",
        )
        for claim in expected:
            with self.subTest(claim=claim):
                self.assertIn(claim, self.page)

    def test_rewritten_copy_does_not_restore_old_phrasing(self) -> None:
        old_phrases = (
            "Wire it, don't script it.",
            "Keep what you own.",
            "Enterprise testing, no enterprise tax.",
            "Build flows by asking.",
            "Grab and go. No rebuild needed.",
            "Stop debugging text mid-run.",
        )
        for phrase in old_phrases:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, self.page)

    def test_contact_script_cache_key_is_current(self) -> None:
        self.assertIn('/contact-form.js?v=3', self.page)


if __name__ == "__main__":
    unittest.main()
