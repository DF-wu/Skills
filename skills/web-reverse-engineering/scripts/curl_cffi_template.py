#!/usr/bin/env python3
"""
curl_cffi template for TLS-fingerprint-protected sites.
Handles retries, proxy rotation, and cookie persistence.

Requires: pip install -U curl_cffi

IMPORTANT (verified against curl_cffi 0.16.3): do NOT paste a Windows User-Agent on top
of a modern Chrome impersonate target. curl_cffi's chrome120+ profiles report a macOS UA,
so overriding it with a Windows string creates a UA-vs-TLS mismatch -- which is itself a
strong detection signal. Let the profile own the UA, or run verify_profile() below to see
what the combination actually reports before you deploy it.
"""
from curl_cffi import requests
import random
import time

# Chrome 109+ randomizes TLS extension order. Reproducing it matters: order-sensitive
# JA3 breaks on modern Chrome without this, and a fixed order while claiming modern
# Chrome is detectable.
EXTRA_FP = {"tls_permute_extensions": True}


def verify_profile(impersonate: str = "chrome") -> dict:
    """Read back what this impersonate target actually claims (UA + TLS hashes).

    Run this BEFORE deploying. The UA platform must match the session you are
    pretending to be; otherwise fix the profile, not the target.
    """
    r = requests.get(
        "https://tls.browserleaks.com/json",
        impersonate=impersonate,
        extra_fp=EXTRA_FP,
        timeout=25,
    )
    data = r.json()
    ua = data.get("user_agent", "")
    if "Macintosh" in ua:
        platform = "macOS"
    elif "Windows" in ua:
        platform = "Windows"
    elif "Android" in ua:
        platform = "Android"
    else:
        platform = "other"
    return {
        "impersonate": impersonate,
        "platform": platform,
        "user_agent": ua,
        "ja3_hash": data.get("ja3_hash"),
        "ja4": data.get("ja4"),
    }


def scrape(url: str, proxy_list: list[str] | None = None, max_retries: int = 3,
           impersonate: str = "chrome") -> str | None:
    """Scrape a URL with TLS fingerprint spoofing.

    Args:
        url: Target URL
        proxy_list: Optional list of proxy URLs for rotation
        max_retries: Max retry attempts
        impersonate: curl_cffi profile; its UA platform is what you are pretending to be

    Returns:
        Response text or None if all retries fail
    """
    session = requests.Session(impersonate=impersonate, extra_fp=EXTRA_FP)

    for attempt in range(max_retries):
        try:
            kwargs = {}
            if proxy_list:
                proxy = random.choice(proxy_list)
                kwargs["proxies"] = {"https": proxy, "http": proxy}

            r = session.get(url, timeout=30, **kwargs)

            if r.status_code == 200:
                return r.text
            elif r.status_code == 403:
                print(f"[Attempt {attempt+1}] 403 Forbidden - may need browser fallback")
                time.sleep(random.uniform(2, 5))
            elif r.status_code == 402:
                # Cloudflare Pay Per Crawl. Retrying cannot help; this is a commercial gate.
                print(f"[Attempt {attempt+1}] 402 Payment Required - commercial gate, not a block")
                print("  Check crawler-* response headers; retrying is pointless here.")
                return None
            else:
                print(f"[Attempt {attempt+1}] Status {r.status_code}")
                time.sleep(random.uniform(1, 3))

        except Exception as e:
            print(f"[Attempt {attempt+1}] Error: {e}")
            time.sleep(random.uniform(2, 5))

    return None


if __name__ == "__main__":
    # First: confirm the profile is coherent, so a later block is not misdiagnosed.
    profile = verify_profile("chrome")
    print(f"Profile: {profile['impersonate']} (UA platform: {profile['platform']})")
    print(f"  JA3 : {profile['ja3_hash']}")
    print(f"  JA4 : {profile['ja4']}")
    print(f"  UA  : {profile['user_agent']}")
    print()

    result = scrape("https://tls.browserleaks.com/json")
    if result:
        import json
        data = json.loads(result)
        print(f"JA3 Hash: {data.get('ja3_hash', 'N/A')}")
        print(f"JA4: {data.get('ja4', 'N/A')}")
        print(f"User-Agent: {data.get('user_agent', 'N/A')}")
