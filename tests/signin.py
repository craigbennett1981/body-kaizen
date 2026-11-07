"""Signing the tests in to a dashboard they started: read the key the server wrote (BK_CONFIG's folder) and send it
as the cookie a browser would hold. Every urllib request in the test run then carries the cookies of every server
signed in so far (each server's cookie is named for its port), the way one browser would."""
import http.cookiejar, os, pathlib, time, urllib.request

_cookies = {}


def key_file(config):
    return pathlib.Path(config).parent / "session.key"


def cookie(port):
    return "; ".join(f"{k}={v}" for k, v in _cookies.items()) if port is None else f"bk_session_{port}={_cookies[f'bk_session_{port}']}"


def sign_in(port, config, wait=15):
    """Wait for the server to write its key, then remember the cookie and install it for urllib. Returns the Cookie
    header value for http.client requests."""
    f = key_file(config); end = time.time() + wait
    while not f.exists() and time.time() < end: time.sleep(0.1)
    _cookies[f"bk_session_{port}"] = f.read_text(encoding="utf-8").strip()
    opener = urllib.request.build_opener()
    opener.addheaders = [("Cookie", "; ".join(f"{k}={v}" for k, v in _cookies.items()))]
    urllib.request.install_opener(opener)
    return cookie(port)


def env(tmp):
    """BK_CONFIG for a test server, in its own temporary folder, so tests never touch your ~/.body-kaizen."""
    return str(pathlib.Path(tmp) / "bk-config" / "config.json")
