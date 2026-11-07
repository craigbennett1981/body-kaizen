"""The README and docs/features.md keep up with the dashboard: every tab is described, every image they show exists,
and every screenshot tools/readme_media.py makes is used somewhere (so none is left to go stale)."""
import pathlib, re, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
README, FEATURES = (ROOT / "README.md").read_text(encoding="utf-8"), (ROOT / "docs" / "features.md").read_text(encoding="utf-8")


class Docs(unittest.TestCase):
    def test_every_tab_is_described(self):
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        tabs = re.findall(r'<button role="tab" data-tab="[a-z]+"[^>]*>([^<]+)</button>', html)
        self.assertGreater(len(tabs), 8)
        for t in tabs:
            with self.subTest(tab=t):
                self.assertRegex(README, rf"\|\s*\*\*[^|]*\b{t}\b", f"{t} isn't in the README's tab table")
                self.assertRegex(FEATURES, rf"(## {t}\b|\*\*{t}:?\*\*|\b{t}\b)", f"{t} isn't in docs/features.md")

    def test_images_exist(self):
        for name, text, base in (("README.md", README, ROOT), ("docs/features.md", FEATURES, ROOT / "docs")):
            for src in re.findall(r'!\[[^\]]*\]\(([^)\s]+)\)|<img[^>]+src="([^"]+)"', text):
                src = next(s for s in src if s)
                if src.startswith("http"): continue
                with self.subTest(doc=name, image=src):
                    self.assertTrue((base / src).exists())

    def test_every_generated_image_is_used(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import importlib; media = importlib.import_module("readme_media")
        used = README + FEATURES
        for f in [s[0] for s in media.SHOTS] + list(media.GIFS):
            with self.subTest(image=f):
                self.assertIn(f"img/{f}", used, f"{f} is generated but nothing shows it")


if __name__ == "__main__":
    unittest.main()
