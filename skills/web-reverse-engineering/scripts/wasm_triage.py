#!/usr/bin/env python3
"""
wasm_triage.py - Triage a WebAssembly module before committing to deep analysis.

Purpose: most WASM analysis time is wasted. This script answers the questions that
determine which analysis route to take, so you do not start decompiling a module you
only needed to hook:

    1. What toolchain built it?      -> determines available symbols and analysis route
    2. What are the imports/exports? -> the JS<->WASM contract; often enough to hook
    3. Is there a name section?      -> if yes, you get real function names for free
    4. Is there DWARF?               -> if yes, feed it to Ghidra and skip decompilation
    5. Which crypto constants appear? -> tells you the algorithm without reading code

It works on raw bytes and needs no external tools, so it runs anywhere Python does.
For deeper work, shell out to wasm-objdump / wasm2wat / wasm2c.

Usage:
    python wasm_triage.py app.wasm
    python wasm_triage.py app.wasm --strings
    python wasm_triage.py app.wasm --json > triage.json
"""

import argparse
import json
import re
import struct
import sys

# Section IDs per the WebAssembly core spec.
SECTION_NAMES = {
    0: "custom",
    1: "type",
    2: "import",
    3: "function",
    4: "table",
    5: "memory",
    6: "global",
    7: "export",
    8: "start",
    9: "element",
    10: "code",
    11: "data",
    12: "datacount",
}

# Toolchain fingerprints. Order matters: check the most specific first.
TOOLCHAIN_MARKERS = [
    ("Emscripten", [b"__wasm_call_ctors", b"emscripten", b"wasi_snapshot_preview1", b"__stack_pointer", b"emscripten_notify_memory_growth"]),
    ("wasm-bindgen (Rust)", [b"__wbindgen_malloc", b"__wbindgen_free", b"__wbindgen_object_drop_ref", b"__wbindgen_exn_store", b"__wbg_", b"__wbindgen_externrefs"]),
    ("AssemblyScript", [b"~lib/rt/", b"__getString", b"__newString", b"ID_OFFSET", b"__setU32", b"__pin"]),
    ("Rust (generic)", [b"rust_begin_unwind", b"core::panicking", b"alloc::alloc", b"__rust_alloc"]),
    ("TinyGo", [b"runtime.alloc", b"tinygo", b"__tinygo_"]),
    ("Zig", [b"__zig_probe_stack", b"std.builtin", b"builtin.default_panic"]),
    ("Blazor/.NET", [b"mono_wasm", b"dotnet", b"System.Private.CoreLib"]),
]

# Crypto fingerprints: (algorithm, marker bytes, note)
CRYPTO_MARKERS = [
    ("AES S-box", bytes([
        0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5,
        0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    ]), "AES implementation present"),
    ("AES inverse S-box", bytes([
        0x52, 0x09, 0x6a, 0xd5, 0x30, 0x36, 0xa5, 0x38,
        0xbf, 0x40, 0xa3, 0x9e, 0x81, 0xf3, 0xd7, 0xfb,
    ]), "AES decryption present"),
    ("SHA-256 IV", bytes.fromhex("6a09e667bb67ae853c6ef372a54ff53a"), "SHA-256 implementation"),
    ("SHA-1 IV", bytes.fromhex("67452301efcdab8998badcfe10325476c3d2e1f0"), "SHA-1 implementation"),
    ("MD5 IV", bytes.fromhex("0123456789abcdeffedcba9876543210"), "MD5 implementation"),
    ("SM3 IV", bytes.fromhex("7380166f4914b2b9172442d7da8a0600"), "Chinese SM3 hash"),
    ("SM4 FK", bytes.fromhex("a3b1bac656aa3350677d9197b27022dc"), "Chinese SM4 cipher"),
    ("ChaCha20 const", b"expand 32-byte k", "ChaCha20 / Salsa20"),
    ("Base64 table", b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/", "standard base64"),
]

# Permuted base64 tables are a strong signal of custom obfuscation.
BASE64_STD = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def read_uleb(data: bytes, pos: int) -> tuple:
    """Read an unsigned LEB128 value. Returns (value, new_pos)."""
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise ValueError("unexpected end of data in LEB128")
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
        if shift > 63:
            raise ValueError("LEB128 too long")
    return result, pos


def parse_sections(data: bytes) -> tuple:
    """Parse the section table. Returns (magic_ok, version, sections)."""
    if len(data) < 8:
        return False, None, []

    if data[:4] != b"\x00asm":
        return False, None, []

    version = struct.unpack("<I", data[4:8])[0]
    sections = []
    pos = 8

    while pos < len(data):
        try:
            section_id = data[pos]
            pos += 1
            size, pos = read_uleb(data, pos)
        except (ValueError, IndexError):
            break

        body = data[pos:pos + size]
        sections.append({
            "id": section_id,
            "name": SECTION_NAMES.get(section_id, f"unknown({section_id})"),
            "size": size,
            "offset": pos,
        })
        pos += size

    return True, version, sections


def safe_repr(raw: bytes, limit: int = 24) -> str:
    """
    Render bytes as pure ASCII so output survives any console encoding.

    Raw crypto constants are arbitrary bytes and would otherwise crash printing on
    non-UTF-8 consoles (e.g. cp950/cp1252 on Windows) with UnicodeEncodeError.
    """
    out = []
    for b in raw[:limit]:
        if 0x20 <= b < 0x7F:
            out.append(chr(b))
        else:
            out.append(f"\\x{b:02x}")
    s = "".join(out)
    if len(raw) > limit:
        s += "..."
    return s


def find_markers(data: bytes, markers: list) -> list:
    """
    Return the labels whose marker bytes appear in data.

    Accepts two entry shapes:
        (label, [needle, ...])            -- toolchain markers
        (label, needle, note)             -- crypto markers
    A bare bytes needle is normalized to a one-element list.
    """
    hits = []
    for entry in markers:
        label = entry[0]
        needles = entry[1]
        extra = entry[2] if len(entry) > 2 else None

        # Normalize: a bare bytes/str marker becomes a single-element list.
        if isinstance(needles, (bytes, bytearray, str)):
            needles = [needles]

        for needle in needles:
            if not isinstance(needle, (bytes, bytearray)):
                continue
            if needle in data:
                hits.append({
                    "label": label,
                    "marker": safe_repr(bytes(needle)),
                    "note": extra,
                })
                break
    return hits


def detect_permuted_base64(data: bytes) -> list:
    """Look for 64-char strings that are permutations of the standard base64 alphabet."""
    found = []
    for match in re.finditer(rb"[A-Za-z0-9+/]{64}", data):
        candidate = match.group(0)
        if candidate == BASE64_STD:
            continue
        if sorted(candidate) == sorted(BASE64_STD):
            found.append({
                "offset": match.start(),
                "table": candidate.decode("ascii", "replace"),
                "note": "permutation of standard base64 alphabet -- custom encoding",
            })
    return found


def extract_strings(data: bytes, min_len: int = 8) -> list:
    """Extract printable ASCII strings."""
    return [m.group(0).decode("ascii", "replace")
            for m in re.finditer(rb"[\x20-\x7e]{%d,}" % min_len, data)]


def main() -> int:
    ap = argparse.ArgumentParser(description="Triage a WebAssembly module.")
    ap.add_argument("wasm", help="path to the .wasm file")
    ap.add_argument("--strings", action="store_true", help="dump printable strings")
    ap.add_argument("--min-string-len", type=int, default=8)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    args = ap.parse_args()

    with open(args.wasm, "rb") as fh:
        data = fh.read()

    magic_ok, version, sections = parse_sections(data)

    if not magic_ok:
        print(f"[!] {args.wasm} is not a WebAssembly module (missing \\0asm magic).")
        print("    If this is a .wat text file, convert it first: wat2wasm file.wat")
        return 2

    toolchains = find_markers(data, TOOLCHAIN_MARKERS)
    cryptos = find_markers(data, CRYPTO_MARKERS)
    permuted = detect_permuted_base64(data)

    # The name section is a custom section (id 0) whose own name string is "name".
    name_section_found = False
    for s in sections:
        if s["id"] == 0:
            body = data[s["offset"]:s["offset"] + s["size"]]
            try:
                nlen, p = read_uleb(body, 0)
                if body[p:p + nlen] == b"name":
                    name_section_found = True
                    break
            except (ValueError, IndexError):
                pass

    dwarf_found = b".debug_info" in data or b".debug_line" in data or b".debug_str" in data

    result = {
        "file": args.wasm,
        "size_bytes": len(data),
        "version": version,
        "sections": sections,
        "toolchains": toolchains,
        "crypto_markers": cryptos,
        "permuted_base64_tables": permuted,
        "has_name_section": name_section_found,
        "has_dwarf": dwarf_found,
    }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print(f"=== WASM triage: {args.wasm} ===")
    print(f"  size    : {len(data)} bytes")
    print(f"  version : {version}")
    print()

    print("--- Sections ---")
    for s in sections:
        print(f"  id={s['id']:<2} {s['name']:<10} {s['size']:>9} bytes")
    print()

    print("--- Toolchain detection ---")
    if toolchains:
        for t in toolchains:
            print(f"  [+] {t['label']}  (marker: {t['marker']})")
    else:
        print("  [ ] no recognized toolchain markers -- possibly stripped or custom")
    print()

    print("--- Crypto markers ---")
    if cryptos:
        for c in cryptos:
            print(f"  [+] {c['label']:<22} {c['note']}")
    else:
        print("  [ ] none found")
    print()

    if permuted:
        print("--- Custom base64 tables ---")
        for p in permuted:
            print(f"  [!] offset {p['offset']}: {p['table']}")
            print(f"      {p['note']}")
        print()

    print("--- Debug info ---")
    print(f"  name section : {'YES' if name_section_found else 'no'}")
    print(f"  DWARF        : {'YES' if dwarf_found else 'no'}")
    print()

    print("=== Recommended route ===")
    if dwarf_found:
        print("  DWARF present -> load directly in Ghidra with nneonneo/ghidra-wasm-plugin.")
        print("  You may get near-original function names and types. Do this FIRST.")
    elif name_section_found:
        print("  Name section present -> wasm2wat keeps function names; read WAT directly.")
    elif cryptos:
        print("  Crypto markers found -> you likely only need to identify the algorithm and key.")
        print("  Try: hook imports + read linear memory (no decompilation needed).")
    else:
        print("  Nothing conclusive -> hook imports and read linear memory first.")
        print("  Only decompile if you actually need to understand control flow.")

    print()
    print("Next commands:")
    print(f"  wasm-objdump -x {args.wasm}          # full structure")
    print(f"  wasm2wat {args.wasm} -o out.wat      # text form")
    print(f"  wasm2c {args.wasm} -o out.c && gcc -O3 ...   # then load in IDA/Ghidra")
    print(f"  wasm2js {args.wasm} -o out.js        # flatten to JS (often fastest)")

    if args.strings:
        print()
        print("--- Strings ---")
        for s in extract_strings(data, args.min_string_len):
            print(f"  {s}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
