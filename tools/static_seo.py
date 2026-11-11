"""Search and link-preview extras for the static demo (tools/export_static.py). Only the exported site gets these;
the dashboard you run at home is unchanged.

Each page gets a title and description written for search results, a canonical URL, Open Graph and Twitter cards
(so a shared link shows the preview image), and a favicon. The demo's home page also gets structured data
(schema.org SoftwareApplication and SoftwareSourceCode) and a visible "About Body Kaizen" section with real text and
links, because everything else on it is drawn by JavaScript from made-up data. Pages that shouldn't be found in
search (the doctor's print view, Connections, the 404 page) are marked noindex.
"""
import html as H, json, os

REPO = "https://github.com/craigbennett1981/body-kaizen"

PAGES = {
    "index.html": dict(
        # The words the page itself uses most (calories, protein, fat, fibre, sleep, training, body) belong in the
        # title, the description and the headings, so search engines can tell what the page is about.
        title="Body Kaizen: free calorie, protein, sleep and training dashboard",
        description="Free, private health dashboard on your computer: calories, protein, carbs, fat and fibre, "
                    "sleep, training, body fat and glucose, logged by chatting to an AI.",
        heading="Body Kaizen live demo: a calorie, protein, sleep and training dashboard",
        index=True, about=True),
    "thresholds.html": dict(
        title="How Body Kaizen judges your numbers: every target and its source",
        description="Every target and score in Body Kaizen and the guideline behind it: protein, saturated fat, "
                    "blood pressure, ApoB, HbA1c, VO2 max, sleep and more.",
        index=True),
    "doctor.html": dict(title="Body Kaizen: doctor's summary (demo)", description="A printable summary for a doctor, from demo data.", index=False),
    "connections.html": dict(title="Body Kaizen: connections (demo)", description="Garmin and LibreLinkUp logins. Not available in the demo.", index=False),
}

ICONS = ("favicon.ico", "favicon.svg", "apple-touch-icon.png", "icon-192.png", "icon-512.png")   # the logo, from app/static

ABOUT = """
<section class="bk-about" aria-labelledby="bk-about-h">
  <h2 id="bk-about-h">About Body Kaizen: a free, private calorie, protein and sleep tracker</h2>
  <p><strong>Body Kaizen is a free, open-source health dashboard that runs on your own computer.</strong> You tell an AI
  assistant such as Claude what you ate, send it a photo of a nutrition label or a screenshot of your scale, and it
  writes everything into plain files in your own private git repository. Body Kaizen works out calories and macros,
  pulls in your Garmin watch, FreeStyle Libre glucose and gym data, and shows how your day, week and months are going
  against the targets you set. No account, no cloud, no telemetry.</p>
  <p>This page is a live demo on 90 days of made-up data for Sam, a fictional person. It sets no cookies, has no
  analytics or trackers, and sends nothing anywhere: everything you see comes from static files on this site.
  Every tab works:</p>
  <ul>
    <li><strong>Day:</strong> calories, protein, carbs, fat, saturated fat and fibre paced through the day, readiness, energy balance and a timeline with glucose under each meal.</li>
    <li><strong>Food:</strong> where your saturated fat, protein and fibre come from, plants per week, swaps from foods you already eat, and glucose by food.</li>
    <li><strong>Sleep &amp; recovery:</strong> readiness, HRV and resting heart rate, sleep stages, sleep debt, when to be in bed tonight, and which of your days go with your worst nights.</li>
    <li><strong>Training:</strong> every session with coach notes and heart rate, lift progression, a muscle map and an activity calendar.</li>
    <li><strong>Experiments:</strong> test one change, like an earlier bedtime or less salt, and see what it does to your own sleep, blood pressure or weight.</li>
    <li><strong>Body, Week, History and Longevity:</strong> body composition and blood pressure, each week against your targets, what changed and when, blood markers and a health score.</li>
  </ul>
  <p><a href="{repo}">Body Kaizen on GitHub</a> · <a href="{repo}#quick-start">Quick start</a> ·
  <a href="{repo}/blob/main/docs/features.md">Every page explained</a> · <a href="thresholds.html">How your numbers are judged</a> ·
  <a href="{repo}/blob/main/DISCLAIMER.md">Disclaimer</a>. A wellness tool, not medical advice or a medical device.</p>
</section>
<noscript><p>The dashboard needs JavaScript to draw its charts. Everything above describes what it shows; the code and
screenshots are on <a href="{repo}">GitHub</a>.</p></noscript>
<style>.bk-about{{max-width:900px;margin:48px auto 24px;padding:20px 22px;border:1px solid var(--rule,#2a2f3a);border-radius:14px;
background:var(--surface,#161a22);color:var(--muted,#a9b0bd);font-size:14px;line-height:1.55}}
.bk-about h2{{margin:0 0 8px;color:var(--ink,#eef1f6);font-size:18px}} .bk-about strong{{color:var(--ink,#eef1f6)}}
.bk-about a{{color:var(--accent,#4F7FEA)}} .bk-about ul{{padding-left:20px}}</style>
"""


def base_url():
    """Where the site lives: BK_SITE_URL (the project's demo.bodykaizen.app), else the GitHub Pages address of the
    repository Actions is building."""
    if os.environ.get("BK_SITE_URL"): return os.environ["BK_SITE_URL"].rstrip("/") + "/"
    repo = os.environ.get("GITHUB_REPOSITORY", "craigbennett1981/body-kaizen")
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/"


def json_ld(base):
    app = {"@type": "SoftwareApplication", "@id": base + "#app", "name": "Body Kaizen", "url": base,
           "description": PAGES["index.html"]["description"], "applicationCategory": "HealthApplication",
           "applicationSubCategory": "Nutrition and fitness tracker", "operatingSystem": "macOS, Linux, Windows",
           "isAccessibleForFree": True, "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
           "screenshot": base + "social-preview.png", "license": "https://www.apache.org/licenses/LICENSE-2.0",
           "featureList": ["Calorie and macro tracking by chat with an AI assistant", "Sleep stage and sleep debt analysis",
                           "Garmin Connect sync", "FreeStyle Libre continuous glucose", "Workout progression and muscle map",
                           "Body composition and energy balance", "Longevity markers and a health score",
                           "Local only: plain files in your own git repository"],
           "sameAs": [REPO]}
    code = {"@type": "SoftwareSourceCode", "name": "Body Kaizen", "codeRepository": REPO, "programmingLanguage": "Python",
            "runtimePlatform": "Python 3.10+", "license": "https://www.apache.org/licenses/LICENSE-2.0", "targetProduct": {"@id": base + "#app"}}
    site = {"@type": "WebSite", "name": "Body Kaizen live demo", "url": base, "inLanguage": "en-GB"}
    return json.dumps({"@context": "https://schema.org", "@graph": [app, code, site]}, indent=1)


def head(page, base):
    m = PAGES[page]; url = base + ("" if page == "index.html" else page); img = base + "social-preview.png"
    t, d = H.escape(m["title"]), H.escape(m["description"])
    tags = [f"<title>{t}</title>", f'<meta name="description" content="{d}">',
            f'<meta name="robots" content="{"index,follow,max-image-preview:large" if m["index"] else "noindex,follow"}">',
            f'<link rel="canonical" href="{url}">',
            '<meta name="theme-color" content="#111318">', '<meta name="color-scheme" content="dark">',
            '<meta property="og:type" content="website">', '<meta property="og:site_name" content="Body Kaizen">',
            f'<meta property="og:title" content="{t}">', f'<meta property="og:description" content="{d}">',
            f'<meta property="og:url" content="{url}">', f'<meta property="og:image" content="{img}">',
            '<meta property="og:image:width" content="1280">', '<meta property="og:image:height" content="640">',
            '<meta property="og:image:alt" content="The Body Kaizen dashboard: macros paced through the day, sleep, training and health markers">',
            '<meta property="og:locale" content="en_GB">', '<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:title" content="{t}">', f'<meta name="twitter:description" content="{d}">',
            f'<meta name="twitter:image" content="{img}">']
    if page == "index.html": tags.append(f'<script type="application/ld+json">\n{json_ld(base)}\n</script>')
    return "\n".join(tags)


def apply(html, page, base):
    """Swap the page's own <title> for the full set of tags, add the About section to the home page."""
    import re
    if page not in PAGES: return html
    html = re.sub(r"<title>.*?</title>", lambda _: head(page, base), html, count=1, flags=re.S)
    html = html.replace('<html lang="en"', '<html lang="en-GB"', 1)
    if PAGES[page].get("heading"):
        # The page's top heading: the brand in the header becomes the h1, naming what the page is (the visible text
        # stays "Body Kaizen"; the rest is read by screen readers and search engines, and it describes the page honestly).
        html = re.sub(r'<div class="brand">Body Kaizen(.*?)</div>',
                      lambda m: f'<h1 class="brand" style="margin:0;font-size:22px;line-height:inherit">Body Kaizen'
                                f'<span class="bk-sr" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap">'
                                f'{H.escape(PAGES[page]["heading"][len("Body Kaizen"):])}</span>{m.group(1)}</h1>', html, count=1, flags=re.S)
    if PAGES[page].get("about"):
        anchor = '<footer class="site-foot">' if '<footer class="site-foot">' in html else '<script src="app.js"></script>'
        html = html.replace(anchor, ABOUT.format(repo=REPO) + anchor, 1)   # after the dashboard, before its footer
    return html


def extras(out, base, built):
    """The logo files, sitemap, a 404 page, and the share image."""
    import shutil, pathlib
    code = pathlib.Path(__file__).resolve().parent.parent
    for f in ICONS: shutil.copy(code / "app" / "static" / f, out / f)
    shutil.copy(code / "docs" / "img" / "social-preview.png", out / "social-preview.png")
    urls = [base + ("" if p == "index.html" else p) for p, m in PAGES.items() if m["index"]]
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
        "".join(f"  <url><loc>{u}</loc><lastmod>{built}</lastmod></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    (out / "404.html").write_text(f"""<!doctype html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Page not found · Body Kaizen</title>
<meta name="robots" content="noindex"><link rel="icon" href="{base}favicon.svg" type="image/svg+xml">
<style>body{{background:#111318;color:#eef1f6;font:16px/1.5 system-ui,sans-serif;display:grid;place-items:center;min-height:90vh;margin:0}}
a{{color:#4F7FEA}}</style></head><body><main><h1>Page not found</h1><p><a href="{base}">Open the Body Kaizen live demo</a> or
see it on <a href="{REPO}">GitHub</a>.</p></main></body></html>
""", encoding="utf-8")
