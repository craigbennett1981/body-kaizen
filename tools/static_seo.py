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
        title="Body Kaizen: private health dashboard for food, sleep and training",
        description="Free, open-source health dashboard that runs on your own computer: macros, sleep, Garmin, "
                    "glucose, workouts and longevity, logged by chatting with an AI.",
        index=True, about=True),
    "thresholds.html": dict(
        title="How Body Kaizen judges your numbers: every target and its source",
        description="Every target and score in Body Kaizen and the guideline behind it: protein, saturated fat, "
                    "blood pressure, ApoB, HbA1c, VO2 max, sleep and more.",
        index=True),
    "doctor.html": dict(title="Body Kaizen: doctor's summary (demo)", description="A printable summary for a doctor, from demo data.", index=False),
    "connections.html": dict(title="Body Kaizen: connections (demo)", description="Garmin and LibreLinkUp logins. Not available in the demo.", index=False),
}

FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#2F5BEA"/>
<path d="M14 44 L26 32 L34 40 L50 22" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M40 21 H51 V32" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></svg>
"""

ABOUT = """
<section class="bk-about" aria-labelledby="bk-about-h">
  <h2 id="bk-about-h">About Body Kaizen</h2>
  <p><strong>Body Kaizen is a free, open-source health dashboard that runs on your own computer.</strong> You tell an AI
  assistant such as Claude what you ate, send it a photo of a nutrition label or a screenshot of your scale, and it
  writes everything into plain files in your own private git repository. Body Kaizen works out calories and macros,
  pulls in your Garmin watch, FreeStyle Libre glucose and gym data, and shows how your day, week and months are going
  against the targets you set. No account, no cloud, no telemetry.</p>
  <p>This page is a live demo on 90 days of made-up data for Sam, a fictional person. It sets no cookies, has no
  analytics or trackers, and sends nothing anywhere: everything you see comes from static files on this site.
  Every tab works:</p>
  <ul>
    <li><strong>Day:</strong> macros paced through the day, readiness, energy balance and a timeline with glucose under each meal.</li>
    <li><strong>Food:</strong> where your saturated fat, protein and fibre come from, plants per week, and swaps from foods you already eat.</li>
    <li><strong>Sleep:</strong> sleep stages, sleep debt, when to be in bed tonight, and which of your days go with your worst nights.</li>
    <li><strong>Training:</strong> every session with coach notes and heart rate, lift progression, a muscle map and an activity calendar.</li>
    <li><strong>Body, Recovery, Trends and Longevity:</strong> body composition, HRV and resting heart rate, targets over time, blood markers and a health score.</li>
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
            f'<link rel="canonical" href="{url}">', '<link rel="icon" href="favicon.svg" type="image/svg+xml">',
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
    if PAGES[page].get("about"):
        anchor = '<footer class="site-foot">' if '<footer class="site-foot">' in html else '<script src="app.js"></script>'
        html = html.replace(anchor, ABOUT.format(repo=REPO) + anchor, 1)   # after the dashboard, before its footer
    return html


def extras(out, base, built):
    """favicon, sitemap, a 404 page, and the share image."""
    import shutil, pathlib
    code = pathlib.Path(__file__).resolve().parent.parent
    (out / "favicon.svg").write_text(FAVICON, encoding="utf-8")
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
