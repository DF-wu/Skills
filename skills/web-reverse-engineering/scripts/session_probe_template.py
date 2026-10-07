#!/usr/bin/env python3
"""
Read-only authenticated-session probe.

Inject a manually-exported session cookie into Camoufox, pass Cloudflare once, then map a
CF-gated SPA's API via in-page fetch (same-origin -> carries cookies + CF clearance) plus
JS-chunk grep. GET-only: safe to run without triggering writes / consuming quotas.

See references/authenticated-session-mapping.md for the full playbook.

Usage:
    1. Export the target's cookies (Cookie-Editor JSON) to cookies.json
    2. Edit BASE / DASHBOARD / CANDIDATE_GETS / PAGES below
    3. python session_probe_template.py cookies.json

Requires (only to actually probe): pip install -U camoufox[geoip] && python -m camoufox fetch

--help and --check-deps work without camoufox installed. The import is deliberately lazy
so that an eager failure does not hide the interface from someone who has not installed
the browser bundle yet.
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

__version__ = "1.0.0"

BASE = "https://example.com"
DASHBOARD = f"{BASE}/dashboard"
# Login-check endpoint: NextAuth/Auth.js -> /api/auth/session ; Discourse -> /session/current.json
SESSION_CHECK = f"{BASE}/api/auth/session"
# Candidate API endpoints to GET (old + guessed-new). Read-only only.
CANDIDATE_GETS = [
    "/api/auth/session", "/api/user/info",
    "/api/checkin/status", "/api/dashboard/stats",
]
# SPA page routes whose JS chunks we grep for real /api/ literals + data-model field names.
PAGES = ["/dashboard"]


def normalize(raw: dict) -> dict | None:
    """Browser-export cookie -> Playwright add_cookies format. Ignores hostOnly/session/storeId."""
    if not raw.get("name") or raw.get("value") is None or not raw.get("domain"):
        return None
    c = {
        "name": str(raw["name"]), "value": str(raw["value"]), "domain": str(raw["domain"]),
        "path": str(raw.get("path") or "/"),
        "secure": bool(raw.get("secure", False)), "httpOnly": bool(raw.get("httpOnly", False)),
    }
    exp = raw.get("expires", raw.get("expirationDate"))
    if exp is not None:
        try:
            c["expires"] = float(exp)
        except (TypeError, ValueError):
            pass
    ss = raw.get("sameSite")
    if ss is not None:
        c["sameSite"] = {"lax": "Lax", "strict": "Strict", "none": "None",
                         "no_restriction": "None"}.get(str(ss).lower(), ss)
    return c


IN_PAGE_FETCH = """async ({m, u, h, b}) => {
    const opts = {method: m, headers: h || {}, credentials: 'include'};
    if (m !== 'GET' && b != null) opts.body = b;
    const r = await fetch(u, opts);
    const t = await r.text();
    return {status: r.status, text: t, ct: r.headers.get('content-type') || ''};
}"""


async def req(page, url, method="GET", headers=None, body=None):
    return await page.evaluate(IN_PAGE_FETCH, {"m": method, "u": url, "h": headers, "b": body})


def check_deps(verbose: bool = True) -> bool:
    """Report whether camoufox is importable, without starting a browser."""
    try:
        import camoufox  # noqa: F401
        ok = True
    except ImportError:
        ok = False
    if verbose:
        if ok:
            print("[ok] camoufox")
        else:
            print("[missing] camoufox -- required only for actual probing.")
            print("          install with: pip install -U camoufox[geoip]")
            print("          then:         python -m camoufox fetch")
            print("          --help and --check-deps work without it.")
    return ok


async def main(cookie_file: str) -> int:
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError:
        print("ERROR: camoufox not installed. Run: pip install -U camoufox[geoip]")
        print("       then fetch the browser bundle: python -m camoufox fetch")
        return 1

    path = Path(cookie_file)
    if not path.exists():
        print(f"ERROR: cookie file not found: {cookie_file}")
        print("       export cookies as Cookie-Editor JSON and pass the path as the first argument.")
        return 2

    try:
        with path.open(encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not parse {cookie_file}: {exc}")
        return 2

    if not isinstance(raw, list):
        print("ERROR: cookie file must be a JSON array (Cookie-Editor export format).")
        return 2

    cookies = [c for c in (normalize(r) for r in raw) if c]
    print(f"injecting {len(cookies)} cookies: {[c['name'] for c in cookies]}")

    async with AsyncCamoufox(headless="virtual", humanize=True) as browser:
        ctx = await browser.new_context()
        await ctx.add_cookies(cookies)
        page = await ctx.new_page()

        await page.goto(DASHBOARD, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(6000)  # let any CF interstitial clear
        print(f"url={page.url} title={await page.title()!r}")

        print("\n== session check ==")
        print(await req(page, SESSION_CHECK))

        print("\n== candidate GETs ==")
        for path in CANDIDATE_GETS:
            r = await req(page, f"{BASE}{path}")
            print(f"  {path:42} -> {r['status']} [{r['ct'][:24]}] {r['text'][:160]!r}")

        print("\n== JS-chunk grep for real /api/ endpoints ==")
        seen: set[str] = set()
        for pp in PAGES:
            html = (await req(page, f"{BASE}{pp}"))["text"]
            chunks = sorted(set(re.findall(r'/_next/static/[^"\'<>\s]+?\.js', html)))
            for cp in chunks[:80]:
                js = (await req(page, urljoin(BASE, cp)))["text"]
                seen |= set(re.findall(r'["\'`](/api/[a-zA-Z0-9/_\-]+)["\'`]', js))
        for a in sorted(seen):
            print(f"  {a}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Read-only authenticated-session probe (GET-only).",
        epilog="Requires camoufox only for probing; --help/--version/--check-deps do not.",
    )
    ap.add_argument("cookies", nargs="?", default="cookies.json",
                    help="path to a Cookie-Editor JSON export (default: cookies.json)")
    ap.add_argument("--version", action="version", version=f"session_probe_template {__version__}")
    ap.add_argument("--check-deps", action="store_true",
                    help="report whether camoufox is installed, then exit")
    return ap


if __name__ == "__main__":
    args = build_parser().parse_args()
    if args.check_deps:
        raise SystemExit(0 if check_deps() else 1)
    raise SystemExit(asyncio.run(main(args.cookies)))
