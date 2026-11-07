"""Regenerate the README's GIFs and the screenshots in docs/, from the demo, so they always show the current code.

    python tools/readme_media.py            # everything, into docs/img/
    python tools/readme_media.py --only sleep.gif food.png

It exports the static demo (tools/export_static.py), serves it locally and drives it in Chromium: screenshots are
clipped to one section of a page, GIFs are recorded as video while the script scrolls, clicks and hovers, then
converted with ffmpeg. Needs Playwright with Chromium, and ffmpeg. Only demo data is ever shown.

Not regenerated here: claude-loop.gif (a chat), setup.png and connections.png (pages the demo doesn't serve),
social-preview.png.
"""
import argparse, os, pathlib, shutil, subprocess, sys, tempfile, time

CODE = pathlib.Path(__file__).resolve().parent.parent
IMG = CODE / "docs" / "img"
sys.path[:0] = [str(CODE / "tests"), str(CODE / "tools")]

# ---------- screenshots: (file, tab, first element, last element, scroll offset); "h2:Text" picks a heading ----------
SHOTS = [
    ("day.png", "day", None, None, 0),
    ("day-timeline.png", "day", "h2:Timeline", "#daytl", 0),
    ("glucose.png", "day", "#glucose", "#glucose", 0),
    ("food.png", "food", "h2:Where it came from", ".staples", 0),
    ("food-plants-swaps.png", "food", "h2:Plants this week", ".sw-grid", 0),
    ("sleep.png", "sleep", "#tab-sleep h1", "#sl-hyp", 0),
    ("sleep-stages.png", "sleep", "h2:Sleep stages", "#sl-stg", 0),
    ("sleep-factors.png", "sleep", "h2:What goes with better", ".sl-fx", 0),
    ("workout.png", "training", "h2:Workouts", "#wodetail", 0),
    ("muscle-map.png", "training", "h2:Muscles worked", "#musclemap", 0),
    ("activity.png", "training", "h2:Activity", "#actcal", 0),
    ("recovery.png", "recovery", "h2:Sleep, HRV", "#recchart", 0),
    ("composition.png", "body", "h2:Body composition", "#bcgrid", 0),
    ("energy-balance.png", "body", "h2:Energy balance", "#ebchart", 0),
    ("trends.png", "trends", None, None, 0),
    ("longevity.png", "longevity", None, None, 0),
]

# ---------- the README's preview: the Day page with an "open the demo" button over it, linked to the live demo ----------
PREVIEW = ("demo-preview.png", "day")
PREVIEW_OVERLAY = """(() => {
  const o = document.createElement('div');
  o.style.cssText = 'position:fixed;inset:0;z-index:99;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;' +
    'padding-bottom:64px;gap:12px;background:linear-gradient(to bottom,rgba(17,19,24,0) 35%,rgba(17,19,24,.55) 62%,rgba(17,19,24,.96) 100%)';
  o.innerHTML = '<div style="display:flex;align-items:center;gap:14px;padding:16px 30px;border-radius:999px;background:#2F5BEA;color:#fff;' +
    'font:700 26px/1 Archivo,system-ui,sans-serif;box-shadow:0 10px 34px rgba(47,91,234,.45)"><span style="font-size:22px">&#9654;</span>Open the live demo</div>' +
    '<div style="color:#C9CFDA;font:500 17px/1.4 Archivo,system-ui,sans-serif">demo.bodykaizen.app &nbsp;·&nbsp; the real dashboard on made-up data &nbsp;·&nbsp; every tab works</div>';
  document.body.append(o);
})()"""

CAPTION_CSS = ("position:fixed;left:0;right:0;bottom:0;z-index:99;padding:14px 20px;background:rgba(17,19,24,.94);"
               "border-top:3px solid #4F7FEA;color:#EBEEF5;font:600 20px/1.3 Archivo,system-ui,sans-serif;text-align:center")


class Page:
    """Helpers over a Playwright page on the served demo."""
    def __init__(self, pg): self.pg = pg

    def tab(self, t, wait=1400):
        self.pg.click(f'nav button[data-tab="{t}"]'); self.pg.wait_for_timeout(wait); self.clean()

    def clean(self):
        self.pg.evaluate("document.querySelectorAll('.toast,#bk-demo-banner').forEach(e => e.remove())")

    def el(self, sel):
        if sel.startswith("h2:"):
            return self.pg.locator("main > section:not([hidden]) h2", has_text=sel[3:]).first
        return self.pg.locator(sel).first

    def y(self, sel):
        return self.pg.evaluate("e => e.getBoundingClientRect().top + scrollY", self.el(sel).element_handle())

    def scroll(self, to, ms=1200, offset=70):
        """Ease the page to an element (or a y position), at a speed a viewer can follow."""
        y = to if isinstance(to, (int, float)) else self.y(to) - offset
        self.pg.evaluate("""([y, ms]) => new Promise(done => { const y0 = scrollY, t0 = performance.now();
            const step = t => { const k = Math.min(1, (t - t0) / ms), e = k < .5 ? 2*k*k : 1 - (-2*k + 2)**2 / 2;
              scrollTo(0, y0 + (y - y0) * e); k < 1 ? requestAnimationFrame(step) : done(); }; requestAnimationFrame(step); })""", [y, ms])

    def caption(self, text):
        self.pg.evaluate("""([t, css]) => { let c = document.getElementById('bk-cap');
            if(!c){ c = document.createElement('div'); c.id = 'bk-cap'; c.style.cssText = css; document.body.append(c); }
            c.textContent = t; }""", [text, CAPTION_CSS])

    def hover(self, sel, fx=.5, fy=.5, steps=12):
        b = self.el(sel).bounding_box()
        self.pg.mouse.move(b["x"] + b["width"] * fx, b["y"] + b["height"] * fy, steps=steps)

    def sweep(self, sel, fy=.4, a=.15, z=.85, ms=1600):
        """Move the mouse across a chart so its tooltip follows."""
        b = self.el(sel).bounding_box(); n = 24
        for i in range(n + 1):
            self.pg.mouse.move(b["x"] + b["width"] * (a + (z - a) * i / n), b["y"] + b["height"] * fy)
            self.pg.wait_for_timeout(ms // n)


# ---------- GIFs: each a function that drives the page while it's recorded ----------

def gif_tour(P):
    pg = P.pg
    P.caption("Day: every macro paced through the day, against today's targets"); pg.wait_for_timeout(1800)
    P.scroll("h2:Timeline", 1300); P.caption("One timeline: food, energy, sleep, training and glucose")
    P.sweep("#daytl", fy=.3, ms=1650); pg.mouse.move(5, 5)
    P.tab("food", 900); P.caption("Food: where your saturated fat, protein and fibre really come from"); pg.wait_for_timeout(1500)
    P.scroll("h2:Plants this week", 1200); P.caption("Plants this week, and swaps from foods you already eat"); pg.wait_for_timeout(1800)
    P.tab("sleep", 900); P.caption("Sleep: last night, your sleep debt, and when to be in bed tonight"); pg.wait_for_timeout(1650)
    P.scroll("h2:Sleep stages", 1300); P.caption("Your sleep stages, and what changes them"); pg.wait_for_timeout(1350)
    P.scroll("h2:What goes with better", 1200); P.caption("Your own nights compared: what goes with the bad ones"); pg.wait_for_timeout(1800)
    P.tab("training", 900); P.caption("Training: every session with coach notes and heart rate"); P.scroll("h2:Workouts", 900)
    chips = pg.locator("#wopick button[data-k]")
    for i in (1, 2): chips.nth(i).click(); pg.wait_for_timeout(825)
    P.scroll("h2:Muscles worked", 1000); P.caption("A muscle map of the hard sets you did")
    P.hover("#musclemap", .3, .35); pg.wait_for_timeout(675); P.hover("#musclemap", .72, .55); pg.wait_for_timeout(825)
    P.tab("body", 900); P.scroll("h2:Body composition", 900); P.caption("Body: weight, composition and energy balance"); pg.wait_for_timeout(1650)
    P.tab("longevity", 900); P.caption("Longevity: blood markers, fitness and a health score"); pg.wait_for_timeout(1950)


def gif_food(P):
    pg = P.pg
    P.tab("food", 900); P.scroll("h2:Every food", 1000)
    box = pg.locator("#fq"); box.click()
    for ch in "chicken": box.type(ch); pg.wait_for_timeout(110)
    pg.wait_for_timeout(1200); box.fill(""); box.dispatch_event("input"); pg.wait_for_timeout(500)
    pg.click('.seg button[data-w="week"]'); pg.wait_for_timeout(1200)
    pg.click('#ftab th[data-k="sf"]'); pg.wait_for_timeout(1400)
    pg.click('#ftab th[data-k="p"]'); pg.wait_for_timeout(1400)
    pg.click('.seg button[data-w="all"]'); pg.wait_for_timeout(1000)
    P.scroll(0, 1200); pg.wait_for_timeout(1500)


def gif_sleep(P):
    pg = P.pg
    P.tab("sleep", 1000); pg.wait_for_timeout(1500)
    P.sweep("#sl-hyp", fy=.5, ms=1800); pg.mouse.move(5, 5)
    P.scroll("h2:Every night", 1100); P.sweep("#sl-trend", fy=.35, ms=1800); pg.mouse.move(5, 5)
    P.scroll("h2:Sleep stages", 1200); pg.wait_for_timeout(1600)
    P.scroll("h2:What goes with better", 1200); pg.wait_for_timeout(2000)
    P.scroll("h2:What your data says", 1100); pg.wait_for_timeout(2000)


def gif_training(P):
    pg = P.pg
    P.tab("training", 1000); P.scroll("h2:Workouts", 900)
    chips = pg.locator("#wopick button[data-k]")
    for i in range(1, 4): chips.nth(i).click(); pg.wait_for_timeout(1100)
    P.scroll("h2:Muscles worked", 1000)
    for m in ("14", "28", "7"): pg.click(f'#mrange button[data-m="{m}"]'); pg.wait_for_timeout(900)
    P.hover("#musclemap", .28, .3); pg.wait_for_timeout(1000); P.hover("#musclemap", .7, .6); pg.wait_for_timeout(1200)
    P.scroll("h2:Calories burnt", 1000); P.sweep("#trainchart", fy=.3, ms=1800)


GIFS = {"tour.gif": (gif_tour, 800, "day"), "food.gif": (gif_food, 680, "food"), "sleep.gif": (gif_sleep, 680, "sleep"),
        "training.gif": (gif_training, 680, "training")}   # file: (script, width, tab it opens on)


def to_gif(video, out, width, skip=1.0, fps=6):
    """Video -> GIF. Scrolling makes every frame new, so: a modest frame rate, duplicate frames dropped while the page
    is still, one palette for the clip and no dithering (dither noise defeats GIF compression)."""
    vf = (f"mpdecimate=hi=512:lo=256:frac=0.5,fps={fps},scale={width}:-1:flags=lanczos,split[a][b];"
          f"[a]palettegen=max_colors=64:stats_mode=full[p];[b][p]paletteuse=dither=none:diff_mode=rectangle")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(skip), "-i", str(video), "-vf", vf, "-loop", "0", str(out)], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", nargs="*", help="file names to make (default: all)")
    ap.add_argument("--site", help="an already exported demo (default: export a fresh one)")
    ap.add_argument("--out", default=str(IMG))
    ap.add_argument("--keep-video", help="also keep each GIF's recording in this folder")
    A = ap.parse_args()
    want = lambda f: not A.only or f in A.only
    out = pathlib.Path(A.out); out.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="bk-media-"))
    site = pathlib.Path(A.site) if A.site else tmp / "site"
    if not A.site: subprocess.run([sys.executable, str(CODE / "tools" / "export_static.py"), str(site)], check=True)
    import test_static
    from playwright.sync_api import sync_playwright
    srv, root, url = test_static._serve(site.resolve())
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--lang=en-GB"])
            opts = dict(color_scheme="dark", locale="en-GB", timezone_id="UTC")
            if any(want(f) for f, *_ in SHOTS):
                pg = b.new_page(viewport={"width": 1200, "height": 900}, device_scale_factor=1.6, reduced_motion="reduce", **opts)
                pg.goto(url); pg.wait_for_selector("#day h1"); P = Page(pg); P.clean()
                for f, tab, top, bottom, _ in SHOTS:
                    if not want(f): continue
                    P.tab(tab, 1600)
                    if top is None:
                        pg.evaluate("scrollTo(0, 0)"); pg.wait_for_timeout(300)
                        pg.screenshot(path=str(out / f), clip={"x": 0, "y": 0, "width": 1200, "height": 640 if tab == "day" else 900})
                    else:
                        s = pg.locator(f"#tab-{tab}").bounding_box()
                        t = P.el(top).bounding_box(); l = P.el(bottom).bounding_box()
                        y0 = pg.evaluate("scrollY")
                        pg.screenshot(path=str(out / f), full_page=True, clip={"x": s["x"] - 14, "y": t["y"] + y0 - 14, "width": s["width"] + 28,
                                                                             "height": l["y"] + l["height"] - t["y"] + 26})
                    print("wrote", f)
                pg.close()
            if want(PREVIEW[0]):
                pg = b.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5, reduced_motion="reduce", **opts)
                pg.goto(url + "#" + PREVIEW[1]); pg.wait_for_selector("#day h1"); pg.wait_for_timeout(2500); P = Page(pg); P.clean()
                pg.evaluate(PREVIEW_OVERLAY); pg.wait_for_timeout(300)
                pg.screenshot(path=str(out / PREVIEW[0])); pg.close(); print("wrote", PREVIEW[0])
            for f, (fn, width, start) in GIFS.items():
                if not want(f): continue
                vids = tmp / f"v-{f}"; vids.mkdir()
                ctx = b.new_context(viewport={"width": 1280, "height": 800}, record_video_dir=str(vids), record_video_size={"width": 1280, "height": 800}, **opts)
                ctx.add_init_script("addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');"
                                    "s.textContent = '#bk-demo-banner,.toast{display:none!important}'; document.head.append(s); })")
                pg = ctx.new_page(); t0 = time.time()
                pg.goto(url + "#" + start); pg.wait_for_selector(f"#tab-{start}:not([hidden]) h1, #tab-{start}:not([hidden]) h2")
                pg.wait_for_timeout(1800); P = Page(pg); P.clean()
                skip = time.time() - t0
                fn(P); pg.wait_for_timeout(400)
                video = pg.video.path(); ctx.close()
                if A.keep_video: os.makedirs(A.keep_video, exist_ok=True); shutil.copy(video, pathlib.Path(A.keep_video) / (f + ".webm"))
                to_gif(video, out / f, width, skip=round(skip, 1))
                print("wrote", f, f"{(out / f).stat().st_size / 1e6:.1f} MB")
            b.close()
    finally:
        srv.shutdown(); srv.server_close(); shutil.rmtree(root, ignore_errors=True); shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
