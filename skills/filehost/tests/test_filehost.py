"""Offline unit tests for scripts/filehost (no network). Run: python3 tests/test_filehost.py"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.dont_write_bytecode = True  # loading the scripts must not drop __pycache__ into the skill dirs

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "filehost"


def load():
    spec = importlib.util.spec_from_loader("filehost", importlib.machinery.SourceFileLoader("filehost", str(SCRIPT)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fh = load()
RAW = "https://h/raw/tok"  # fake site base (never a real token)


class FakeClient:
    """Answers just enough of ncloud.Client for one published site; records write calls."""

    def __init__(self, item_type="folder", path="/filehost/demo", served=None, size=0):
        self.cfg = SimpleNamespace(url="https://h")
        self.item_type, self.path, self.served, self.size = item_type, path, served or {}, size
        self.calls = []

    def ocs(self, method, path, **kw):
        self.calls.append(("ocs", method, path))
        if method == "GET":
            return [{"id": 7, "share_type": 3, "path": self.path, "item_type": self.item_type, "token": "tok"}]
        return {}

    def app_json(self, method, path, data=None, **kw):
        self.calls.append(("app_json", method, path))
        doc = {"shareId": 7, "token": "tok", "enabled": True, "rawOnly": False, "csp": None, "rawUrl": RAW}
        return {"shares": [doc]} if "raw-shares/" in path else doc

    def fileid(self, path):
        return 42

    def exists(self, path):
        return path.endswith("/index.html") and any(u.endswith("/index.html") for u in self.served)

    def propfind(self, path, depth="1", props=None, url=None):
        return [{"path": path, "is_dir": False, "size": self.size}]

    def request(self, method, url, headers=None, auth=True, **kw):
        body = self.served.get(url)
        return (404, {}, b"") if body is None else (200, {"content-type": "x/test"}, body)

    def mkcol(self, path, parents=False):
        self.calls.append(("mkcol", path))

    def dav(self, method, url, **kw):
        self.calls.append(("dav", method, url))
        return 201, {}, b""

    def put_file(self, local, path, keep_mtime=True):
        self.calls.append(("put_file", path))

    def put(self, path, data, mtime=None, content_type=None):
        self.calls.append(("put", path))


def run(fn, c, argv):
    """Run a command function, return (exit code, parsed JSON stdout)."""
    out = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            fn(c, fh.build_parser().parse_args(argv))
        except SystemExit as e:
            code = e.code
    text = out.getvalue()
    return code, (json.loads(text) if text.strip().startswith("{") else text)


class TestFilehost(unittest.TestCase):
    def test_finds_sibling_nextcloud_use(self):
        self.assertTrue(fh.find_ncloud().is_file())
        for name in ("raw_set", "upload_dir", "walk_local", "DEFAULT_EXCLUDES", "list_tree"):
            self.assertTrue(hasattr(fh.nc, name), name)
        self.assertIn("site", fh.nc.CSP_PRESETS)
        self.assertTrue(sys.dont_write_bytecode)

    def test_nextcloud_use_cli_pin(self):
        with mock.patch.dict(os.environ, {"NEXTCLOUD_USE_CLI": "/nonexistent/ncloud"}):
            with self.assertRaises(SystemExit) as cm:
                fh.find_ncloud()
            self.assertIn("NEXTCLOUD_USE_CLI", str(cm.exception.code))
        real = fh.find_ncloud()
        with mock.patch.dict(os.environ, {"NEXTCLOUD_USE_CLI": str(real)}):
            self.assertEqual(fh.find_ncloud(), real)

    def test_missing_nextcloud_use_env_is_an_error(self):
        with mock.patch.dict(os.environ, {"NEXTCLOUD_USE_ENV": "/nonexistent/env"}):
            if not getattr(fh.nc.Config(), "env_error", None):
                self.skipTest("this ncloud copy has no Config.env_error")
            with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as cm:
                fh.main(["presets"])
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("NEXTCLOUD_USE_ENV", err.getvalue())

    def test_sanitize_name(self):
        self.assertEqual(fh.sanitize_name("My Site!"), "My-Site")
        self.assertEqual(fh.sanitize_name("/reports/2026-10/"), "reports/2026-10")
        self.assertEqual(fh.sanitize_name("報告 v2"), "報告-v2")
        self.assertEqual(fh.sanitize_name("..hidden.."), "hidden")

    def test_site_path(self):
        self.assertEqual(fh.site_path("/filehost", "demo"), "/filehost/demo")
        self.assertEqual(fh.site_path("filehost/", "a/b"), "/filehost/a/b")

    def test_inject_base(self):
        html = b"<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>"
        out = fh.inject_base(html, "https://h/raw/T/index.html")
        self.assertIn(b'<head><base href="https://h/raw/T/index.html">', out)
        self.assertEqual(fh.inject_base(out, "https://other"), out)  # idempotent
        self.assertTrue(fh.inject_base(b"<p>no head</p>", "https://h/").startswith(b'<base href="https://h/">'))

    def test_index_hashes_accept_plain_and_injected(self):
        html = b"<html><head></head><body>x</body></html>"
        url = RAW + "/index.html"
        ok = fh.index_hashes(html, url)
        self.assertIn(fh.sha256(html), ok)
        self.assertIn(fh.sha256(fh.inject_base(html, url)), ok)
        self.assertNotIn(fh.sha256(fh.inject_base(html, "https://other/index.html")), ok)
        self.assertNotIn(fh.sha256(b"stale"), ok)

    def test_auto_preset(self):
        self.assertEqual(fh.auto_preset(Path("/tmp/x.html")), "site")
        self.assertEqual(fh.auto_preset(Path("/tmp/x.svg")), "site")
        self.assertIsNone(fh.auto_preset(Path("/tmp/x.png")))
        self.assertEqual(fh.auto_preset(Path("/tmp")), "site")

    def test_site_url(self):
        self.assertEqual(fh.site_url(RAW, "folder"), RAW + "/index.html")
        self.assertEqual(fh.site_url(RAW, "folder", "/"), RAW + "/index.html")
        self.assertEqual(fh.site_url(RAW, "file"), RAW)
        self.assertEqual(fh.site_url(RAW, "folder", "docs/"), RAW + "/docs/")          # trailing slash kept
        self.assertEqual(fh.site_url(RAW, "folder", "/docs"), RAW + "/docs")
        self.assertEqual(fh.site_url(RAW, "folder", "img/a b#1?.png"), RAW + "/img/a%20b%231%3F.png")
        self.assertEqual(fh.site_url(RAW, "folder", "報告/"), RAW + "/%E5%A0%B1%E5%91%8A/")

    def test_local_files_sorted_and_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            for rel in ("b.txt", "a/z.png", ".git/config", "node_modules/x.js", "c.log"):
                (Path(d) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(d) / rel).write_text(rel)
            self.assertEqual(fh.local_files(Path(d)), ["a/z.png", "b.txt", "c.log"])
            self.assertEqual(fh.local_files(Path(d), ["*.log"]), ["a/z.png", "b.txt"])

    def test_parser(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FILEHOST_ROOT", None)
            p = fh.build_parser()
        a = p.parse_args(["publish", "./dist", "--name", "demo", "--preset", "cdn", "--raw-only", "--prune", "--yes"])
        self.assertEqual(a.name, "demo")
        self.assertEqual(a.preset, "cdn")
        self.assertTrue(a.raw_only and a.prune and a.yes)
        self.assertEqual(a.root, fh.DEFAULT_ROOT)

    def test_root_before_and_after_subcommand(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FILEHOST_ROOT", None)
            p = fh.build_parser()
        self.assertEqual(p.parse_args(["--root", "/a", "list"]).root, "/a")
        self.assertEqual(p.parse_args(["list", "--root", "/b"]).root, "/b")
        self.assertEqual(p.parse_args(["--root", "/a", "info", "x"]).root, "/a")   # subparser must not clobber it
        self.assertEqual(p.parse_args(["publish", "./d", "--root", "/c"]).root, "/c")
        self.assertEqual(p.parse_args(["list"]).root, fh.DEFAULT_ROOT)
        with mock.patch.dict(os.environ, {"FILEHOST_ROOT": "/env"}):
            self.assertEqual(fh.build_parser().parse_args(["verify", "x"]).root, "/env")

    def test_prune_requires_yes(self):
        p = fh.build_parser()
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as cm:
                fh.cmd_publish(None, p.parse_args(["publish", d, "--prune"]))  # dies before any network call
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("--yes", err.getvalue())
            fh.prune_gate(p.parse_args(["publish", d, "--prune", "--dry-run"]))
            fh.prune_gate(p.parse_args(["publish", d, "--prune", "--yes"]))
            fh.prune_gate(p.parse_args(["publish", d]))

    def test_publish_folder_without_index(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "b.json").write_text("{}")
            (Path(d) / "a b.png").write_bytes(b"PNG")
            c = FakeClient(served={RAW + "/a%20b.png": b"PNG", RAW: b"null"})
            code, res = run(fh.cmd_publish, c, ["publish", d, "--name", "demo", "--json"])
            self.assertEqual(code, 0, res)
            self.assertEqual(res["url"], RAW + "/a%20b.png")
            self.assertEqual(res["short_url"], RAW)
            self.assertTrue(res["ok"] and res["verify"]["content_matches_local"])
            c.served[RAW + "/a%20b.png"] = b"changed"
            code, res = run(fh.cmd_publish, c, ["publish", d, "--name", "demo", "--json"])
            self.assertEqual(code, 2)
            self.assertFalse(res["ok"])

    def test_publish_inject_base_verifies_injected_bytes(self):
        html = b"<html><head></head><body>hi</body></html>"
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.html").write_bytes(html)
            c = FakeClient(served={RAW + "/index.html": fh.inject_base(html, RAW + "/index.html")})
            code, res = run(fh.cmd_publish, c, ["publish", d, "--name", "demo", "--inject-base", "--json"])
            self.assertEqual(code, 0, res)
            self.assertEqual(res["url"], RAW + "/index.html")
            self.assertIn(("put", "/filehost/demo/index.html"), c.calls)

    def test_verify_local_accepts_inject_base_variant(self):
        html = b"<html><head></head><body>hi</body></html>"
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.html").write_bytes(html)
            for served in (html, fh.inject_base(html, RAW + "/index.html")):
                code, res = run(fh.cmd_verify, FakeClient(served={RAW + "/index.html": served}), ["verify", "demo", "--local", d])
                self.assertEqual(code, 0, res)
                self.assertTrue(res["content_matches_local"])
            code, res = run(fh.cmd_verify, FakeClient(served={RAW + "/index.html": b"old"}), ["verify", "demo", "--local", d])
            self.assertEqual(code, 2)
            self.assertFalse(res["content_matches_local"])

    def test_verify_local_asset_folder_probes_first_file(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "x.json").write_text("[1]")
            code, res = run(fh.cmd_verify, FakeClient(served={RAW + "/x.json": b"[1]"}), ["verify", "demo", "--local", d])
            self.assertEqual(code, 0, res)
            self.assertEqual(res["url"], RAW + "/x.json")

    def test_url_command(self):
        c = FakeClient()
        self.assertEqual(run(fh.cmd_url, c, ["url", "demo"])[1].strip(), RAW + "/index.html")
        self.assertEqual(run(fh.cmd_url, c, ["url", "demo", "docs/"])[1].strip(), RAW + "/docs/")
        self.assertEqual(run(fh.cmd_url, c, ["url", "demo", "a b.png"])[1].strip(), RAW + "/a%20b.png")

    def test_list_points_asset_folders_at_first_file(self):
        class AssetFolder(FakeClient):
            def propfind(self, path, depth="1", props=None, url=None):
                return [{"path": path, "is_dir": True}, {"path": f"{path}/b.json", "is_dir": False},
                        {"path": f"{path}/a b.txt", "is_dir": False}]

        code, res = run(fh.cmd_list, AssetFolder(), ["list", "--json"])
        rec = json.loads(res)[0]
        self.assertEqual((rec["url"], rec["base"], rec["has_index"]), (RAW + "/a%20b.txt", RAW, False))
        code, res = run(fh.cmd_list, FakeClient(served={RAW + "/index.html": b"x"}), ["list", "--json"])
        rec = json.loads(res)[0]
        self.assertEqual((rec["url"], rec["has_index"]), (RAW + "/index.html", True))

    def test_info_single_file_site(self):
        c = FakeClient(item_type="file", path="/filehost/logo/logo.png", size=1234)
        code, res = run(fh.cmd_info, c, ["info", "logo"])
        self.assertEqual((res["files"], res["bytes"]), (1, 1234))
        self.assertEqual(res["url"], RAW)


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=1))
