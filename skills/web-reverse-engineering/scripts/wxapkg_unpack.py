#!/usr/bin/env python3
"""
wxapkg_unpack.py - Minimal, dependency-free WeChat mini-program (wxapkg) unpacker.

Purpose: unpack a wxapkg into its constituent files, and report the package type
so you can decide which toolchain to use next. This is a reference implementation
you can read and modify -- the heavy lifting for decryption/repacking should use
KillWxapkg (Go) or wedecode (Node).

Format reference (18-byte header, struct format '>BIIIBI'):
    header:
        firstMark         1 byte   0xBE
        info              4 bytes  usually 0
        indexInfoLength   4 bytes
        bodyInfoLength    4 bytes
        lastMark          1 byte   0xED
        fileCount         4 bytes
    index (repeated fileCount times):
        nameLength        4 bytes
        name              Char[nameLength]
        offset            4 bytes
        size              4 bytes
    data:
        file contents, concatenated

Usage:
    python wxapkg_unpack.py __APP__.wxapkg -o out/
    python wxapkg_unpack.py app.wxapkg --list          # just list contents
    python wxapkg_unpack.py app.wxapkg --verify        # parse header only
"""

import argparse
import os
import struct
import sys

FIRST_MARK = 0xBE
LAST_MARK = 0xED

# firstMark(1) + info(4) + indexInfoLength(4) + bodyInfoLength(4) + lastMark(1) + fileCount(4)
HEADER_SIZE = 18


class WxapkgError(Exception):
    pass


def parse_header(data: bytes) -> dict:
    """Parse and validate the wxapkg header. Raises WxapkgError on mismatch."""
    if len(data) < HEADER_SIZE:
        raise WxapkgError(f"file too small ({len(data)} bytes) to contain a header")

    # Bytes 0-13: firstMark(1) + info(4) + indexInfoLength(4) + bodyInfoLength(4) + lastMark(1)
    first_mark, info, index_len, body_len, last_mark = struct.unpack(">BIIIB", data[:14])
    # Bytes 14-17: fileCount
    file_count = struct.unpack(">I", data[14:HEADER_SIZE])[0]

    if first_mark != FIRST_MARK:
        raise WxapkgError(
            f"firstMark is 0x{first_mark:02x}, expected 0x{FIRST_MARK:02x}. "
            "This is not a wxapkg, or it has been transformed."
        )
    if last_mark != LAST_MARK:
        raise WxapkgError(
            f"lastMark is 0x{last_mark:02x}, expected 0x{LAST_MARK:02x}."
        )

    return {
        "first_mark": first_mark,
        "info": info,
        "index_info_length": index_len,
        "body_info_length": body_len,
        "last_mark": last_mark,
        "file_count": file_count,
        "header_size": HEADER_SIZE,
    }


def parse_index(data: bytes, header: dict) -> list:
    """Parse the file index. Returns a list of {name, offset, size} dicts."""
    pos = header["header_size"]
    end = pos + header["index_info_length"]
    files = []

    for i in range(header["file_count"]):
        if pos + 4 > end:
            raise WxapkgError(f"index truncated while reading name length of file #{i}")

        name_len = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4

        if pos + name_len > end:
            raise WxapkgError(f"index truncated while reading name of file #{i}")

        name = data[pos:pos + name_len].decode("utf-8", errors="replace")
        pos += name_len

        if pos + 8 > end:
            raise WxapkgError(f"index truncated while reading offset/size of file #{i}")

        offset, size = struct.unpack(">II", data[pos:pos + 8])
        pos += 8

        files.append({"name": name, "offset": offset, "size": size})

    return files


def classify(files: list) -> str:
    """Best-effort package classification from the file list."""
    names = {f["name"] for f in files}
    lower = {n.lower() for n in names}

    if any(n.startswith("__plugin__") or "plugin" in n for n in lower):
        return "plugin package"
    if any("subpackage" in n or "subpackages" in n for n in lower):
        return "subpackage"
    if "app-service.js" in lower and "app-config.json" in lower:
        return "main package (standard)"
    if any(n.endswith(".js") for n in lower):
        return "likely main package"
    return "unrecognized layout"


def safe_join(base: str, name: str) -> str:
    """
    Join base and name, refusing to escape base.

    Extracted archives are untrusted input: a crafted wxapkg could contain
    '../../etc/passwd' style names. Never write outside the output directory.
    """
    target = os.path.normpath(os.path.join(base, name))
    base_abs = os.path.abspath(base)
    target_abs = os.path.abspath(target)
    if not (target_abs == base_abs or target_abs.startswith(base_abs + os.sep)):
        raise WxapkgError(f"refusing to write outside output dir: {name!r}")
    return target_abs


def extract(data: bytes, files: list, out_dir: str, data_start: int) -> tuple:
    """Write each indexed file to out_dir. Returns (written, skipped)."""
    written = 0
    skipped = []

    for entry in files:
        start = data_start + entry["offset"]
        end = start + entry["size"]

        if end > len(data):
            skipped.append((entry["name"], f"truncated (needs {end}, have {len(data)})"))
            continue

        try:
            dest = safe_join(out_dir, entry["name"])
        except WxapkgError as exc:
            skipped.append((entry["name"], str(exc)))
            continue

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(data[start:end])
        written += 1

    return written, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description="Unpack a WeChat mini-program .wxapkg file.")
    ap.add_argument("wxapkg", help="path to the .wxapkg file")
    ap.add_argument("-o", "--out", default="wxapkg_out", help="output directory")
    ap.add_argument("--list", action="store_true", help="list contents without extracting")
    ap.add_argument("--verify", action="store_true", help="parse and validate the header only")
    args = ap.parse_args()

    with open(args.wxapkg, "rb") as fh:
        data = fh.read()

    print(f"[*] read {len(data)} bytes from {args.wxapkg}")

    try:
        header = parse_header(data)
    except WxapkgError as exc:
        print(f"[!] header parse failed: {exc}")
        print()
        print("If this is a real mini-program package, it is likely encrypted or uses a")
        print("non-standard container. Use KillWxapkg (auto-decrypt) or wedecode instead:")
        print("  https://github.com/Ackites/KillWxapkg")
        print("  https://github.com/biggerstar/wedecode")
        return 2

    print("[+] header OK")
    print(f"    firstMark        : 0x{header['first_mark']:02x}")
    print(f"    info             : {header['info']}")
    print(f"    indexInfoLength  : {header['index_info_length']}")
    print(f"    bodyInfoLength   : {header['body_info_length']}")
    print(f"    lastMark         : 0x{header['last_mark']:02x}")
    print(f"    fileCount        : {header['file_count']}")

    if args.verify:
        return 0

    try:
        files = parse_index(data, header)
    except WxapkgError as exc:
        print(f"[!] index parse failed: {exc}")
        return 2

    print(f"[+] index OK, {len(files)} entries")
    print(f"[+] layout guess   : {classify(files)}")

    if args.list:
        print()
        total = 0
        for f in files:
            total += f["size"]
            print(f"    {f['size']:>9}  {f['name']}")
        print(f"\n    {len(files)} files, {total} bytes total")
        return 0

    data_start = header["header_size"] + header["index_info_length"]
    written, skipped = extract(data, files, args.out, data_start)

    print(f"[+] wrote {written} files to {args.out}")
    if skipped:
        print(f"[!] skipped {len(skipped)}:")
        for name, why in skipped:
            print(f"    {name}: {why}")

    print()
    print("[i] Next: the output usually contains large app-service.js / app-config.json")
    print("    rather than per-page files. If this was a subpackage, you must also pass")
    print("    the MAIN package directory to your tool (the -s flag), or the restored")
    print("    wxml will be missing components.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
