#!/usr/bin/env python3
"""Rewrite README.md's relative links and images as absolute GitHub URLs, so they work on PyPI.

usage: python tools/pypi_readme.py REF     (a tag such as v0.4.0; the release workflow runs this before building)

GitHub resolves README.md's relative links itself; PyPI shows the same file with nowhere to resolve them against.
Edits README.md in place: run it on a release checkout, never commit the result.
"""
import pathlib, re, sys

REPO = "craigbennett1981/body-kaizen"
README = pathlib.Path(__file__).resolve().parent.parent / "README.md"

def absolute(ref, text):
    blob, raw = f"https://github.com/{REPO}/blob/{ref}/", f"https://raw.githubusercontent.com/{REPO}/{ref}/"
    def fix(target, image):
        if re.match(r"[a-z]+:|#|/", target): return target   # already absolute, or an anchor on this page
        return (raw if image or re.search(r"\.(png|gif|jpe?g|svg)(#|$)", target) else blob) + target
    text = re.sub(r'(src=")([^"]+)(")', lambda m: m[1] + fix(m[2], True) + m[3], text)
    return re.sub(r"(\]\()([^)\s]+)(\))", lambda m: m[1] + fix(m[2], False) + m[3], text)

if __name__ == "__main__":
    if len(sys.argv) != 2: sys.exit(__doc__)
    README.write_text(absolute(sys.argv[1], README.read_text()))
