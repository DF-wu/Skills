#!/usr/bin/env python3
"""
Camoufox template for high-protection sites.
Anti-detection Firefox automation with human-like behavior.

Requires (only to actually scrape):
    pip install -U camoufox[geoip]
    python -m camoufox fetch          # download the patched browser bundle

--help and --check-deps work without camoufox installed; the import inside the scrape
functions is deliberately lazy so the interface stays discoverable before setup.
"""
import argparse
import random
import sys
import time

__version__ = "1.0.0"


def check_deps(verbose: bool = True) -> bool:
    """Report whether camoufox is importable, without launching a browser."""
    try:
        import camoufox  # noqa: F401
        ok = True
    except ImportError:
        ok = False
    if verbose:
        if ok:
            print("[ok] camoufox")
        else:
            print("[missing] camoufox -- required only for actual scraping.")
            print("          install with: pip install -U camoufox[geoip]")
            print("          then:         python -m camoufox fetch")
            print("          --help and --check-deps work without it.")
    return ok


def scrape_with_camoufox(
    url: str,
    proxy: dict | None = None,
    humanize: bool = True,
    wait_for: str = "networkidle",
    screenshot: str | None = None,
) -> str:
    """Scrape a URL using Camoufox anti-detection browser.
    
    Args:
        url: Target URL
        proxy: Proxy config dict {"server": "...", "username": "...", "password": "..."}
        humanize: Enable human-like behavior simulation
        wait_for: Playwright wait state ("networkidle", "domcontentloaded", "load")
        screenshot: Optional path to save screenshot
    
    Returns:
        Page HTML content
    """
    from camoufox.sync_api import Camoufox
    
    kwargs = {"humanize": humanize}
    if proxy:
        kwargs["proxy"] = proxy
    
    with Camoufox(**kwargs) as browser:
        page = browser.new_page()
        page.goto(url, wait_until=wait_for)
        
        # Simulate human browsing behavior
        time.sleep(random.uniform(1, 3))
        _simulate_human(page)
        
        if screenshot:
            page.screenshot(path=screenshot, full_page=True)
        
        content = page.content()
        return content


def _simulate_human(page):
    """Add human-like interactions to avoid behavioral detection."""
    try:
        # Random mouse movement
        page.mouse.move(random.randint(100, 500), random.randint(100, 400))
        time.sleep(random.uniform(0.3, 0.8))
        
        # Scroll down a bit
        page.evaluate(f"window.scrollBy(0, {random.randint(100, 400)})")
        time.sleep(random.uniform(0.5, 1.5))
        
        # Another mouse movement
        page.mouse.move(random.randint(200, 600), random.randint(200, 500))
    except Exception:
        pass  # Non-critical, continue


def scrape_with_cf_clearance(
    target_url: str,
    proxy: dict | None = None,
) -> tuple[str, dict]:
    """Get cf_clearance cookie from Cloudflare-protected site, then return both content and cookies.
    
    Use the returned cookies with curl_cffi for subsequent fast HTTP requests.
    
    Returns:
        Tuple of (page_content, cookies_dict)
    """
    from camoufox.sync_api import Camoufox
    
    kwargs = {"humanize": True}
    if proxy:
        kwargs["proxy"] = proxy
    
    with Camoufox(**kwargs) as browser:
        page = browser.new_page()
        page.goto(target_url, wait_until="networkidle")
        
        time.sleep(random.uniform(2, 5))
        _simulate_human(page)
        
        # Extract cookies
        cookies = page.context.cookies()
        cookie_dict = {c["name"]: c["value"] for c in cookies}
        
        content = page.content()
        return content, cookie_dict


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Camoufox anti-detection scraping template.",
        epilog="Requires camoufox only for scraping; --help/--version/--check-deps do not.",
    )
    ap.add_argument("--url", default="https://bot.sannysoft.com/",
                    help="target URL (default: the bot-detection self-test page)")
    ap.add_argument("--screenshot", help="optional path to save a full-page screenshot")
    ap.add_argument("--cf-clearance", action="store_true",
                    help="also extract cookies via scrape_with_cf_clearance()")
    ap.add_argument("--version", action="version", version=f"camoufox_template {__version__}")
    ap.add_argument("--check-deps", action="store_true",
                    help="report whether camoufox is installed, then exit")
    return ap


if __name__ == "__main__":
    args = build_parser().parse_args()

    if args.check_deps:
        sys.exit(0 if check_deps() else 1)

    if not check_deps(verbose=False):
        print("ERROR: camoufox not installed. Run: pip install -U camoufox[geoip]")
        print("       then fetch the browser bundle: python -m camoufox fetch")
        sys.exit(1)

    html = scrape_with_camoufox(args.url, screenshot=args.screenshot)
    print(f"Page length: {len(html)} chars")

    if args.cf_clearance:
        # Get Cloudflare cookies for reuse with a fast HTTP client:
        #   from curl_cffi import requests
        #   r = requests.get(url, impersonate="chrome", cookies=cookies)
        _content, cookies = scrape_with_cf_clearance(args.url)
        print(f"Cookies obtained: {sorted(cookies)}")
