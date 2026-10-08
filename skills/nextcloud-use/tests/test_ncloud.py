"""Offline unit tests for scripts/ncloud (no network). Run: python3 -m pytest tests/ or python3 tests/test_ncloud.py"""
import contextlib
import http.server
import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.dont_write_bytecode = True  # never drop __pycache__ into the skill directory

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "ncloud"


def load():
    spec = importlib.util.spec_from_loader("ncloud", importlib.machinery.SourceFileLoader("ncloud", str(SCRIPT)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nc = load()

MULTISTATUS = b"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:s="http://sabredav.org/ns" xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns">
 <d:response>
  <d:href>/remote.php/dav/files/alice/%e6%97%85%e8%a1%8c%e8%b3%87%e6%96%99/</d:href>
  <d:propstat><d:prop>
    <d:resourcetype><d:collection/></d:resourcetype>
    <oc:fileid>123</oc:fileid><oc:permissions>RGDNVCK</oc:permissions>
    <oc:share-types><oc:share-type>3</oc:share-type></oc:share-types>
    <d:getlastmodified>Fri, 18 Sep 2026 14:33:56 GMT</d:getlastmodified>
  </d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat>
  <d:propstat><d:prop><d:getcontentlength/></d:prop><d:status>HTTP/1.1 404 Not Found</d:status></d:propstat>
 </d:response>
 <d:response>
  <d:href>/remote.php/dav/files/alice/%e6%97%85%e8%a1%8c%e8%b3%87%e6%96%99/a%20b.pdf</d:href>
  <d:propstat><d:prop>
    <d:resourcetype/><d:getcontentlength>42</d:getcontentlength><d:getcontenttype>application/pdf</d:getcontenttype>
    <d:getetag>"abc"</d:getetag><oc:fileid>124</oc:fileid><oc:favorite>1</oc:favorite>
  </d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat>
 </d:response>
</d:multistatus>"""


class TestHelpers(unittest.TestCase):
    def test_quote_path_keeps_slashes_and_encodes_unicode(self):
        self.assertEqual(nc.quote_path("/旅行/a b.pdf"), "/%E6%97%85%E8%A1%8C/a%20b.pdf")

    def test_norm_path(self):
        self.assertEqual(nc.norm_path("foo/bar/"), "/foo/bar")
        self.assertEqual(nc.norm_path("/"), "")
        self.assertEqual(nc.norm_path(" /x "), "/x")

    def test_parse_multistatus(self):
        entries = nc.parse_multistatus(MULTISTATUS, "alice")
        self.assertEqual(len(entries), 2)
        folder, pdf = entries
        self.assertTrue(folder["is_dir"])
        self.assertEqual(folder["path"], "/旅行資料")
        self.assertEqual(folder["fileid"], 123)
        self.assertEqual(folder["share_types"], [3])
        self.assertFalse(pdf["is_dir"])
        self.assertEqual(pdf["path"], "/旅行資料/a b.pdf")
        self.assertEqual(pdf["size"], 42)
        self.assertEqual(pdf["etag"], "abc")
        self.assertEqual(pdf["favorite"], 1)
        self.assertEqual(pdf["mime"], "application/pdf")

    def test_permission_aliases(self):
        self.assertEqual(nc.PERM_ALIASES["ro"], 1)
        self.assertEqual(nc.PERM_ALIASES["rw"], 15)
        self.assertEqual(nc.PERM_ALIASES["upload"], 4)
        self.assertEqual(nc.PERM_ALIASES["full"], 31)

    def test_csp_presets_are_well_formed(self):
        allowed = {"base-uri", "child-src", "connect-src", "default-src", "font-src", "form-action", "frame-ancestors", "frame-src",
                   "img-src", "manifest-src", "media-src", "object-src", "sandbox", "script-src", "style-src", "upgrade-insecure-requests", "worker-src"}
        for name, csp in nc.CSP_PRESETS.items():
            if not csp:
                continue
            for directive in csp.split(";"):
                directive = directive.strip()
                if directive:
                    self.assertIn(directive.split()[0], allowed, f"{name}: {directive}")
        self.assertEqual(nc.CSP_PRESETS["locked"], "")
        self.assertIn("script-src 'self'", nc.CSP_PRESETS["site"])
        self.assertIn("frame-ancestors *", nc.CSP_PRESETS["embed"])

    def test_embed_is_cdn_plus_frame_ancestors(self):
        cdn = nc.CSP_PRESETS["cdn"].replace("frame-ancestors 'none'", "frame-ancestors *")
        self.assertEqual(nc.CSP_PRESETS["embed"], cdn)

    def test_origin_of(self):
        self.assertEqual(nc.origin_of("https://cloud.example.com/x"), nc.origin_of("https://CLOUD.example.com:443/y"))
        self.assertNotEqual(nc.origin_of("https://cloud.example.com@evil.example/"), nc.origin_of("https://cloud.example.com/"))

    def test_mcp_secret_allowed(self):
        self.assertTrue(nc.mcp_secret_allowed("http://127.0.0.1:18000/mcp"))
        self.assertTrue(nc.mcp_secret_allowed("http://my-mcp:8000/mcp", ("my-mcp",)))
        self.assertFalse(nc.mcp_secret_allowed("http://my-mcp:8000/mcp"))
        self.assertTrue(nc.mcp_secret_allowed("https://mcp.example/mcp"))
        self.assertFalse(nc.mcp_secret_allowed("http://10.0.0.5:18000/mcp"))

    def test_write_secret_is_0600(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "sub" / "env"
            nc.write_secret(target, "X=1\n")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
            self.assertEqual(target.read_text(), "X=1\n")
            self.assertEqual(sorted(x.name for x in target.parent.iterdir()), ["env"])

    def test_fmt_size(self):
        self.assertEqual(nc.fmt_size(0), "0B")
        self.assertEqual(nc.fmt_size(2048), "2.0K")
        self.assertEqual(nc.fmt_size("x"), "-")


class TestConfig(unittest.TestCase):
    def test_env_file_parsing_and_precedence(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "env"
            p.write_text("# comment\nexport NEXTCLOUD_URL='https://x.example/'\nNEXTCLOUD_USER=\"alice\"\nNEXTCLOUD_APP_PASSWORD=pw\nNEXTCLOUD_OCC_MODE=ssh\n")
            old = dict(os.environ)
            try:
                for k in list(os.environ):
                    if k.startswith("NEXTCLOUD_"):
                        del os.environ[k]
                os.environ["NEXTCLOUD_USE_ENV"] = str(p)
                cfg = nc.Config()
                self.assertEqual(cfg.url, "https://x.example")
                self.assertEqual(cfg.user, "alice")
                self.assertEqual(cfg.password, "pw")
                self.assertEqual(cfg.occ_mode, "ssh")
                os.environ["NEXTCLOUD_USER"] = "bob"  # process env wins over file
                self.assertEqual(nc.Config().user, "bob")
            finally:
                os.environ.clear()
                os.environ.update(old)

    def test_require_password_message_names_config_path(self):
        old = dict(os.environ)
        try:
            for k in list(os.environ):
                if k.startswith("NEXTCLOUD_"):
                    del os.environ[k]
            os.environ["XDG_CONFIG_HOME"] = "/nonexistent/xdg"
            os.environ["HOME"] = "/nonexistent"
            cfg = nc.Config()
            with self.assertRaises(nc.NcError) as cm:
                cfg.require_password()
            self.assertIn("/nonexistent/xdg/nextcloud-use/env", str(cm.exception).split("Env files searched")[0])
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_missing_explicit_env_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            xdg = Path(d) / "xdg" / "nextcloud-use"
            xdg.mkdir(parents=True)
            (xdg / "env").write_text("NEXTCLOUD_APP_PASSWORD=other-account\n")
            old = dict(os.environ)
            try:
                for k in list(os.environ):
                    if k.startswith("NEXTCLOUD_"):
                        del os.environ[k]
                os.environ["XDG_CONFIG_HOME"] = str(Path(d) / "xdg")
                os.environ["NEXTCLOUD_USE_ENV"] = str(Path(d) / "missing-env")
                cfg = nc.Config()
                self.assertIsNone(cfg.password)  # no silent fallback to the XDG file
                self.assertIn("does not exist", cfg.env_error)
                with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
                    nc.main(["whoami"])
                self.assertEqual(cm.exception.code, 2)
            finally:
                os.environ.clear()
                os.environ.update(old)


class TestGenericConfig(unittest.TestCase):
    """The skill ships no instance defaults: everything site-specific comes from the environment."""

    def setUp(self):
        self._env = dict(os.environ)
        for k in list(os.environ):
            if k.startswith("NEXTCLOUD_"):
                del os.environ[k]
        os.environ.update({"XDG_CONFIG_HOME": "/nonexistent/xdg", "HOME": "/nonexistent"})

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_url_and_user_are_required(self):
        cfg = nc.Config()
        self.assertEqual(cfg.missing(), ["NEXTCLOUD_URL", "NEXTCLOUD_USER"])
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()) as err:
            nc.main(["ls", "/"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("NEXTCLOUD_URL", err.getvalue())

    def test_occ_off_without_container_or_ssh_host(self):
        os.environ.update({"NEXTCLOUD_URL": "https://cloud.example.com", "NEXTCLOUD_USER": "alice", "NEXTCLOUD_OCC_MODE": "auto",
                           "NEXTCLOUD_OCC_CONTAINER": "no-such-container-for-tests"})
        c = nc.Client(nc.Config())
        self.assertEqual(c.occ_mode(), "off")
        with self.assertRaises(nc.NcError):
            c.occ_argv(["status"])
        self.assertEqual(c.mcp_url(), "http://nextcloud-mcp:8000/mcp")

    def test_occ_command_prefix(self):
        os.environ.update({"NEXTCLOUD_OCC_COMMAND": "sudo -u www-data php /var/www/nextcloud/occ"})
        c = nc.Client(nc.Config())
        self.assertEqual(c.occ_argv(["status"]), ["sudo", "-u", "www-data", "php", "/var/www/nextcloud/occ", "status"])
        os.environ["NEXTCLOUD_OCC_SSH_HOST"] = "nc-host"
        argv = nc.Client(nc.Config()).occ_argv(["status"])
        self.assertEqual(argv[-3:], ["--", "nc-host", "sudo -u www-data php /var/www/nextcloud/occ status"])

    def test_local_mcp_url_uses_port(self):
        os.environ.update({"NEXTCLOUD_OCC_MODE": "local", "NEXTCLOUD_MCP_PORT": "18555"})
        self.assertEqual(nc.Client(nc.Config()).mcp_url(), "http://127.0.0.1:18555/mcp")

    def test_mcp_create_argv_is_hardened_and_env_driven(self):
        os.environ.update({"NEXTCLOUD_URL": "https://cloud.example.com/", "NEXTCLOUD_USER": "alice",
                           "NEXTCLOUD_MCP_CONTAINER": "nc-mcp", "NEXTCLOUD_MCP_PORT": "18001",
                           "NEXTCLOUD_MCP_NETWORK": "agents", "NEXTCLOUD_MCP_APPS": "webdav, deck"})
        argv = nc.mcp_create_argv(nc.Config())
        text = " ".join(argv)
        for part in ("--name nc-mcp", "-p 127.0.0.1:18001:8000", "--network agents", "--cap-drop ALL", "--read-only",
                     "NEXTCLOUD_HOST=https://cloud.example.com", "MCP_DEPLOYMENT_MODE=multi_user_basic",
                     "MCP_ALLOWED_HOSTS=nc-mcp:*,127.0.0.1:*,localhost:*", "--enable-app webdav --enable-app deck"):
            self.assertIn(part, text)
        self.assertNotIn("NEXTCLOUD_PASSWORD", text)
        self.assertNotIn("NEXTCLOUD_USERNAME", text)

    def test_config_init_requires_url_and_user_and_notes(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["NEXTCLOUD_USE_ENV"] = str(Path(d) / "env")
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                nc.main(["config", "init"])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(nc.main(["config", "init", "--url", "https://cloud.example.com/", "--user", "alice",
                                          "--occ-ssh-host", "nc-host"]), 0)
            text = (Path(d) / "env").read_text()
            self.assertIn("NEXTCLOUD_URL=https://cloud.example.com\n", text)
            self.assertIn("NEXTCLOUD_OCC_SSH_HOST=nc-host\n", text)
            (Path(d) / "NOTES.md").write_text("never scan /bob/files/Archive\n")
            with contextlib.redirect_stdout(io.StringIO()) as out:
                nc.main(["config", "notes"])
            self.assertIn("never scan", out.getvalue())


class TestOcc(unittest.TestCase):
    def test_occ_argv_ssh_quoting(self):
        old = dict(os.environ)
        try:
            os.environ["NEXTCLOUD_OCC_MODE"] = "ssh"
            os.environ["NEXTCLOUD_OCC_SSH_HOST"] = "nc-host"
            c = nc.Client(nc.Config())
            argv = c.occ_argv(["config:system:get", "trusted domains", "--output=json"])
            self.assertEqual(argv[:4], ["ssh", "-o", "BatchMode=yes", "-o"])
            self.assertEqual(argv[-3:-1], ["--", "nc-host"])
            self.assertIn("docker exec -i -u www-data -- nextcloud-aio-nextcloud php occ config:system:get 'trusted domains' --output=json", argv[-1])
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_read_only_allow_list(self):
        ro = nc.occ_is_read_only
        self.assertTrue(ro("status", ["--output=json"]))
        self.assertTrue(ro("share:list", ["--owner", "alice"]))
        self.assertTrue(ro("maintenance:mode", []))
        self.assertFalse(ro("maintenance:mode", ["--on"]))
        self.assertTrue(ro("trashbin:size", ["--user", "alice"]))
        self.assertFalse(ro("trashbin:size", ["--user", "alice", "10GB"]))
        self.assertFalse(ro("config:list", ["--private"]))
        for cmd in ("user:delete", "files:scan", "config:system:set", "app:enable", "user:auth-tokens:add", "security:bruteforce:reset"):
            self.assertFalse(ro(cmd, []), cmd)

    def test_allow_list_names_exist_in_index(self):
        known = nc.occ_known_commands()
        self.assertGreater(len(known), 200)
        self.assertEqual(sorted(nc.OCC_READ_ONLY - known), [])

    def test_command_name_skips_global_options(self):
        self.assertEqual(nc.occ_command_name(["-n", "-q", "user:delete", "bob"]), ("user:delete", ["bob"]))
        self.assertEqual(nc.occ_command_name(["--no-ansi"]), (None, []))

    def test_guard_blocks_writes_and_abbreviations_without_yes(self):
        def fake_occ(self_, args, input_data=None, capture=True):
            if args[:1] != ["list"]:
                raise AssertionError(f"occ must not run {args}")
            names = [{"name": n} for n in ("status", "user:delete", "files:scan")]
            return nc.subprocess.CompletedProcess(args, 0, json.dumps({"commands": names}).encode(), b"")

        for args, msg in ((["--", "-n", "user:delete", "bob"], "not on the read-only allow-list"),
                          (["--", "user:del", "bob"], "abbreviations are rejected"),
                          (["--", "files:scan", "alice"], "not on the read-only allow-list")):
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()) as err, \
                    unittest.mock.patch.object(nc.Client, "occ", fake_occ):
                nc.main(["occ"] + args)
            self.assertEqual(cm.exception.code, 1, args)
            self.assertIn(msg, err.getvalue())

    def test_guard_lets_read_only_through(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = nc.main(["occ", "--print-only", "--", "-n", "status", "--output=json"])
        self.assertEqual(rc, 0)
        self.assertIn("php occ -n status --output=json", out.getvalue())


class StubNextcloud(http.server.BaseHTTPRequestHandler):
    """Records requests; answers like a tiny OCS server."""
    log = []

    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        StubNextcloud.log.append({"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body})
        if self.path.startswith("/redirect-away"):
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{self.server.server_port}/landed")
            self.end_headers()
            return
        if "/shares/" in self.path and self.command == "GET":
            data = [{"id": "7", "share_type": 3, "permissions": 17, "path": "/x"}]
        else:
            data = {"id": "7", "share_type": 3, "permissions": 17, "path": "/x", "token": "T", "url": "u"}
        payload = json.dumps({"ocs": {"meta": {"status": "ok", "statuscode": 200}, "data": data}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_DELETE = _handle

    def log_message(self, *args):
        pass


class TestHttpAgainstStub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), StubNextcloud)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        StubNextcloud.log.clear()
        self._env = dict(os.environ)
        for k in list(os.environ):
            if k.startswith("NEXTCLOUD_"):
                del os.environ[k]
        os.environ.update({"NEXTCLOUD_URL": self.url, "NEXTCLOUD_USER": "u", "NEXTCLOUD_APP_PASSWORD": "pw",
                           "XDG_CONFIG_HOME": "/nonexistent", "HOME": "/nonexistent"})

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def run_cli(self, *argv):
        raw = io.BytesIO()
        out, err = io.TextIOWrapper(raw, encoding="utf-8", write_through=True), io.StringIO()  # `call` writes to stdout.buffer
        code = None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = nc.main(list(argv))
            except SystemExit as e:
                code = e.code
        out.flush()
        return code, raw.getvalue().decode("utf-8"), err.getvalue()

    def test_call_form_data(self):
        code, out, err = self.run_cli("call", "POST", "/ocs/v2.php/x", "-d", "a=1", "-d", "b=x y")
        self.assertEqual(code, 0, err)
        self.assertEqual(StubNextcloud.log[-1]["body"], b"a=1&b=x+y")
        self.assertTrue(StubNextcloud.log[-1]["headers"]["Authorization"].startswith("Basic "))

    def test_call_refuses_foreign_origin_with_auth(self):
        code, out, err = self.run_cli("call", "GET", "https://evil.example/steal")
        self.assertEqual(code, 1)
        self.assertIn("foreign origin", err)
        self.assertEqual(StubNextcloud.log, [])

    def test_call_no_auth_sends_no_authorization(self):
        other = self.url.replace("127.0.0.1", "localhost")  # different origin, same stub
        code, out, err = self.run_cli("call", "GET", other + "/public", "--no-auth")
        self.assertEqual(code, 0, err)
        self.assertNotIn("Authorization", StubNextcloud.log[-1]["headers"])

    def test_call_delete_needs_yes(self):
        code, out, err = self.run_cli("call", "DELETE", "/ocs/v2.php/x")
        self.assertEqual(code, 1)
        self.assertEqual(StubNextcloud.log, [])

    def test_redirect_to_other_origin_drops_authorization(self):
        code, out, err = self.run_cli("call", "GET", "/redirect-away")
        self.assertEqual(code, 0, err)
        self.assertIn("Authorization", StubNextcloud.log[0]["headers"])
        self.assertEqual(StubNextcloud.log[1]["path"], "/landed")
        self.assertNotIn("Authorization", StubNextcloud.log[1]["headers"])

    def test_share_create_sends_json_with_password(self):
        os.environ["SHARE_PW"] = "s3cret"
        code, out, err = self.run_cli("share", "create", "/x", "--perm", "ro", "--password", "s3cret", "--label", "l")
        self.assertEqual(code, 0, err)
        req = StubNextcloud.log[-1]
        self.assertEqual(req["headers"]["Content-Type"], "application/json")
        self.assertEqual(json.loads(req["body"]), {"path": "/x", "shareType": 3, "permissions": 1, "password": "s3cret", "label": "l"})

    def test_subcommand_password_never_becomes_the_login(self):
        self.run_cli("share", "create", "/x", "--perm", "ro", "--password", "share-secret")
        self.run_cli("mcp", "credential", "--url", "http://evil.example/mcp")
        import base64
        for req in StubNextcloud.log:
            self.assertEqual(base64.b64decode(req["headers"]["Authorization"][6:]).decode(), "u:pw")
        cfg = nc.Config(nc.build_parser().parse_args(["user", "create", "bob", "--password", "new-user-pw"]))
        self.assertEqual(cfg.password, "pw")
        cfg = nc.Config(nc.build_parser().parse_args(["--password", "override", "ls"]))
        self.assertEqual(cfg.password, "override")

    def test_public_write_link_needs_yes(self):
        code, out, err = self.run_cli("share", "create", "/x", "--perm", "rw")
        self.assertEqual(code, 1)
        self.assertEqual(StubNextcloud.log, [])
        code, out, err = self.run_cli("share", "create", "/x", "--perm", "rw", "--yes")
        self.assertEqual(code, 0, err)

    def test_share_update_widening_needs_yes(self):
        code, out, err = self.run_cli("share", "update", "7", "--clear-password")
        self.assertEqual(code, 1)
        self.assertIn("widens", err)
        self.assertEqual([r["method"] for r in StubNextcloud.log], ["GET"])
        code, out, err = self.run_cli("share", "update", "7", "--label", "x")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(StubNextcloud.log[-1]["body"]), {"label": "x"})

    def test_upload_dir_prune_needs_yes(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, err = self.run_cli("upload-dir", d, "/site", "--prune")
            self.assertEqual(code, 1)
            self.assertIn("--yes", err)
            self.assertEqual(StubNextcloud.log, [])

    def test_doctor_without_password_fails(self):
        del os.environ["NEXTCLOUD_APP_PASSWORD"]
        with unittest.mock.patch.object(nc.Client, "occ_mode", return_value="local"), \
                unittest.mock.patch.object(nc.Client, "occ", side_effect=OSError("no docker in tests")):
            code, out, err = self.run_cli("doctor")
        self.assertEqual(code, 2)
        self.assertIn("password=MISSING", out)
        self.assertIn("skipped", out)

    def test_app_password_needs_yes(self):
        with unittest.mock.patch.object(nc.Client, "occ", side_effect=AssertionError("occ must not run")):
            code, out, err = self.run_cli("app-password", "agent-x")
        self.assertEqual(code, 1)


class TestParser(unittest.TestCase):
    def test_help_builds_and_lists_core_commands(self):
        p = nc.build_parser()
        text = p.format_help()
        for cmd in ("doctor", "ls", "put", "search", "share", "raw", "occ", "mcp", "call", "config"):
            self.assertIn(cmd, text)

    def test_share_create_defaults(self):
        p = nc.build_parser()
        a = p.parse_args(["share", "create", "/x", "--perm", "ro", "--label", "l"])
        self.assertEqual(a.type, "link")
        self.assertEqual(nc.resolve_perm(a.perm), 1)


import unittest.mock  # noqa: E402  (used above; kept explicit for python -m unittest)

if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=1))
