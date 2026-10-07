#!/usr/bin/env python3
"""
fingerprint_probe.py - Verify your client's TLS/HTTP fingerprint BEFORE blaming the target.

Most "the site blocked me" problems are actually "my client does not look like a browser".
This script compares your client's fingerprint against a reference, so you fix the client
first instead of writing bypass code against a problem you do not have.

Usage:
    python fingerprint_probe.py
    python fingerprint_probe.py --impersonate chrome136
    python fingerprint_probe.py --reference browser_ref.json

Requires (only to actually probe): pip install -U curl_cffi

--help, --version, and --check-deps work WITHOUT curl_cffi installed. The import is
deliberately lazy: an eager import at module scope makes --help fail with a dependency
error instead of showing help, which is a poor first experience and hides the interface
from anyone who has not installed the extras yet.
"""

import argparse
import json
import sys

__version__ = "1.0.0"

# Loaded lazily by _load_requests(). See the note above.
_requests = None
_IMPORT_ERROR = None


def _load_requests():
    """Import curl_cffi on first use, caching both the module and any import error."""
    global _requests, _IMPORT_ERROR
    if _requests is not None:
        return _requests
    if _IMPORT_ERROR is not None:
        return None
    try:
        from curl_cffi import requests as _r
        _requests = _r
        return _requests
    except ImportError as exc:
        _IMPORT_ERROR = exc
        return None


def check_deps(verbose: bool = True) -> bool:
    """Report whether the probing dependency is available."""
    ok = _load_requests() is not None
    if verbose:
        if ok:
            try:
                from curl_cffi import __version__ as cc_version
            except Exception:  # noqa: BLE001
                cc_version = "unknown"
            print(f"[ok] curl_cffi {cc_version}")
        else:
            print("[missing] curl_cffi -- required only for actual probing.")
            print("          install with: pip install -U curl_cffi")
            print("          --help, --version, and --check-deps work without it.")
    return ok


# Public fingerprint echo endpoints. Each reports a different slice.
PROBES = {
    "tls_browserleaks": "https://tls.browserleaks.com/json",
    "tls_peet": "https://tls.peet.ws/api/all",
}

# Fields worth diffing between your client and a real browser.
KEY_FIELDS_BROWSERLEAKS = [
    "ja3_hash",
    "ja3n_hash",
    "ja4",
    "akamai_hash",
    "akamai_text",
    "user_agent",
    "http_version",
]


def probe(url: str, impersonate: str, permute: bool, timeout: int = 25) -> dict:
    """Fetch a fingerprint echo endpoint and return parsed JSON."""
    requests = _load_requests()
    if requests is None:
        return {"_error": "curl_cffi not installed; run: pip install -U curl_cffi"}

    extra_fp = {}
    if permute:
        # Chrome 109+ randomizes TLS extension order. Reproducing it matters:
        # order-sensitive JA3 breaks on modern Chrome without this.
        extra_fp["tls_permute_extensions"] = True

    kwargs = {"timeout": timeout, "impersonate": impersonate}
    if extra_fp:
        kwargs["extra_fp"] = extra_fp

    try:
        resp = requests.get(url, **kwargs)
    except Exception as exc:  # noqa: BLE001 - we want to report any transport failure
        return {"_error": f"{type(exc).__name__}: {exc}"}

    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {"_error": "non-JSON response", "_status": resp.status_code, "_body": resp.text[:400]}


def summarize_browserleaks(data: dict) -> dict:
    if "_error" in data:
        return data
    return {k: data.get(k) for k in KEY_FIELDS_BROWSERLEAKS if k in data}


def diff_against_reference(observed: dict, reference: dict) -> list:
    """Return a list of human-readable mismatches."""
    mismatches = []
    for key, ref_val in reference.items():
        obs_val = observed.get(key)
        if obs_val is None:
            continue
        if obs_val != ref_val:
            mismatches.append(f"  {key}:\n    yours = {obs_val}\n    ref   = {ref_val}")
    return mismatches


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify client TLS/HTTP fingerprint.",
        epilog="Requires curl_cffi only for probing; --help/--version/--check-deps do not.",
    )
    ap.add_argument("--version", action="version", version=f"fingerprint_probe {__version__}")
    ap.add_argument("--check-deps", action="store_true",
                    help="report whether the probing dependency is installed, then exit")
    ap.add_argument("--impersonate", default="chrome", help="curl_cffi impersonate target")
    ap.add_argument("--no-permute", action="store_true",
                    help="disable tls_permute_extensions (NOT recommended for modern Chrome targets)")
    ap.add_argument("--reference", help="path to a JSON file of reference values captured from a real browser")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of the report")
    args = ap.parse_args()

    if args.check_deps:
        return 0 if check_deps() else 1

    if _load_requests() is None:
        print("ERROR: curl_cffi not installed. Run: pip install -U curl_cffi")
        print("       (--help and --version work without it)")
        return 1

    permute = not args.no_permute

    if not args.json:
        print(f"=== TLS fingerprint probe (impersonate={args.impersonate}, permute_extensions={permute}) ===\n")

    results = {}
    for name, url in PROBES.items():
        if not args.json:
            print(f"[*] probing {name} ...")
        data = probe(url, args.impersonate, permute)
        results[name] = data
        if args.json:
            continue
        if "_error" in data:
            print(f"    FAILED: {data['_error']}\n")
            continue
        print("    OK\n")

    bl = results.get("tls_browserleaks", {})
    reference = None

    if args.reference:
        try:
            with open(args.reference, "r", encoding="utf-8") as fh:
                reference = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR reading reference file: {exc}")
            return 2

    if args.json:
        payload = {
            "version": __version__,
            "impersonate": args.impersonate,
            "permute_extensions": permute,
            "summary": summarize_browserleaks(bl) if isinstance(bl, dict) else {},
            "raw": results,
        }
        if reference is not None:
            payload["reference"] = reference
            payload["mismatches"] = diff_against_reference(payload["summary"], reference)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if "_error" not in bl and bl:
        summary = summarize_browserleaks(bl)
        print("=== Fingerprint summary ===")
        for k, v in summary.items():
            print(f"  {k:16s} = {v}")
        print()

    if reference is not None:
        observed = summarize_browserleaks(bl)
        mismatches = diff_against_reference(observed, reference)
        print("=== Diff vs reference ===")
        if mismatches:
            print("MISMATCHES FOUND - fix the client before writing any bypass code:")
            for m in mismatches:
                print(m)
        else:
            print("No mismatches. If the target still blocks you, the problem is NOT the transport layer.")
        print()

    print("=== Interpretation ===")
    print("  ja3_hash differs from a real browser  -> order-sensitive JA3; expected on modern Chrome")
    print("  ja3n_hash / ja4 differ                -> cipher or extension SET differs; fix impersonate target")
    print("  akamai_text differs                   -> HTTP/2 SETTINGS or pseudo-header order differs")
    print()
    print("Reminder: spoofing User-Agent WITHOUT matching these values is net-negative.")
    print("The mismatch between UA and fingerprint is itself a strong detection signal.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
