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
        for f in [s[0] for s in media.SHOTS] + list(media.GIFS) + [media.PREVIEW[0]]:
            with self.subTest(image=f):
                self.assertIn(f"img/{f}", used, f"{f} is generated but nothing shows it")


class IntegrationRequests(unittest.TestCase):
    def test_requests_reach_the_integration_form(self):
        """Every "ask for an integration" link leads to the form, never a blank issue. From the dashboard the link opens
        the form directly. From pages read on github.com it goes to the template list instead: GitHub reloads a
        new-issue page opened by a click inside github.com and drops ?template= on the way, landing on a blank issue."""
        form = ROOT / ".github" / "ISSUE_TEMPLATE" / "integration_request.yml"
        self.assertTrue(form.exists())
        link = r"https://github\.com/craigbennett1981/body-kaizen/issues/new[^\s)\"']*"
        for f, want in ((ROOT / "README.md", "/issues/new/choose"), (ROOT / "docs" / "integrations.md", "/issues/new/choose"),
                        (ROOT / "app" / "static" / "connections.html", f"/issues/new?template={form.name}")):
            links = re.findall(link, f.read_text(encoding="utf-8"))
            with self.subTest(file=f.name):
                self.assertTrue(links, "no link to ask for an integration")
                for l in links: self.assertTrue(l.endswith(want), l)


if __name__ == "__main__":
    unittest.main()
