# TROUBLESHOOTING.md - filehost

The working directory is the filehost skill root. In the table `ncloud` means the nextcloud-use CLI
(`../nextcloud-use/scripts/ncloud`) and `filehost` means `scripts/filehost`. `https://cloud.example.com`,
`<share_id>`, `<token>` and `<ip>` are placeholders.

| Symptom | Cause | Fix |
|---|---|---|
| `200`, `content-type: application/json`, body `null` | The folder share has no `index.html` (at `/raw/<token>` or an existing sub-folder URL there is no page to serve; an app bug, not a 404). The share itself is fine | For a web page: add an `index.html` and re-`publish`. For an asset folder: use `/raw/<token>/<file>` (`filehost url <name> <file>`). `publish` / `list` already point `url` at the first file (`list --json` shows `has_index: false`); `filehost url <name>` without a path prints `.../index.html` (404 for such folders) - pass `<file>` |
| `404 Not found`, `content-type: text/plain` | Token not allowed (raw not enabled), share deleted or expired, not a link share, or the file / sub-folder does not exist | `ncloud raw get <share_id>` (check `enabled`); `filehost list`; re-`publish` (re-enables raw) |
| `404`, `content-type: text/html` (Nextcloud page) | The URL shape matched no route: `/raw/<token>/` (trailing slash) or a token with characters outside `[A-Za-z0-9-]` | Use `/raw/<token>/index.html`; give sub-folders a trailing slash |
| Blank page, JS not running, external images/CSS missing | CSP is the fallback (`sandbox; default-src 'none'`) or a too-strict preset; or a misspelled directive in a custom CSP (accepted silently, ignored by the browser) | `filehost csp <name> --preset site` (or `cdn`); add directives from the console's "Refused to ..." messages (CSP.md section 4); confirm the sent CSP with `curl -sI` |
| Old content after an update | Browser/proxy cache (`max-age=300`) | Wait 5 minutes, add `?v=`, force reload; check the origin: `curl -s "$URL" \| sha256sum` vs the local file |
| `verify --local` reports `content_matches_local: false` | Remote differs from local: local edits not re-published yet, `--local` points at the wrong directory, or the last `publish` failed midway (`--inject-base` is not the cause; the injected version is accepted) | Re-`publish`; use the same `--local` directory as for publishing |
| Relative assets 404 (`/raw/style.css`) | The short URL `/raw/<token>` was used | Use `url` (`.../index.html`) or `publish --inject-base` |
| Browser `fetch()` of raw JSON from another site fails (CORS error) | Raw responses send no `Access-Control-Allow-Origin` | Fetch server-side, or host the calling page as a raw page on the same Nextcloud host (same origin) |
| Embedding in another site's iframe is refused | No `frame-ancestors` in the CSP (fallback / `asset`) -> core's `X-Frame-Options: SAMEORIGIN` applies; or `frame-ancestors 'none'` from `site` / `cdn` | `filehost csp <name> --preset embed` |
| `raw-share` POST returns `{"error":"not_found"}` | Share id does not exist, is not type 3, or was not created by / is not owned by the configured user | `ncloud share get <share_id>`; `ncloud raw list <path>` for the right id |
| `csp` POSTed but unchanged in the response | Caller is not in `csp_editor_group` (default `admin`) | Use an account in that group; check `ncloud occ -- config:app:get files_sharing_raw csp_editor_group` |
| A previous `rawOnly` is gone (`/s/<token>` opens again) | A POST without `rawOnly` means false; or raw was disabled (`ncloud raw disable`) - while disabled the app reports `rawOnly:false`, so on re-enable the CLI cannot read the old value and sends false | Set it again: `filehost publish ... --raw-only` or `ncloud raw enable <share_id> --raw-only`; the CSP is unaffected (kept) |
| `ncloud raw enable` prints `warning: raw links are fully public...` on stderr | Normal reminder (raw ignores the share password), not an error | Make sure the content may be public |
| `publish --prune` fails with `error: --prune deletes remote files...` | `--prune` deletes remote files and is refused without `--yes` (same for `ncloud upload-dir --prune`) | Preview with `--prune --dry-run` (works before the remote folder exists); add `--yes` after the user agrees |
| `MKCOL ... 409` during `publish` | Parent folder missing (wrong `--root`) | `ncloud mkdir -p <root>`, or fix `--root` |
| `PUT ... 413` or connection reset during `publish` | A single request too large for a proxy | Files >= 64 MiB use chunked upload automatically; lower the threshold, e.g. `NEXTCLOUD_CHUNK_THRESHOLD_MB=16` |
| `423 Locked` during `publish` | File locked (another client is writing) | Retry later |
| `error: cannot find the nextcloud-use skill` | No `nextcloud-use/scripts/ncloud` in the same skills directory (or the usual skills dirs) | Install nextcloud-use next to filehost (e.g. `npx skills add <repo> -s nextcloud-use -s filehost -g`), or set `NEXTCLOUD_USE_CLI=/path/to/ncloud` |
| `error: NEXTCLOUD_USE_CLI=... is not a file` | `NEXTCLOUD_USE_CLI` is set to a missing path; filehost never falls back to another copy | Fix the path or `unset NEXTCLOUD_USE_CLI` |
| `error: NEXTCLOUD_URL, NEXTCLOUD_USER not set: configure nextcloud-use first` | nextcloud-use is not configured in this runtime | `ncloud config init --url https://cloud.example.com --user alice --app-password ...`, or export the variables |
| `NEXTCLOUD_USE_ENV=... does not exist`, or the app password is missing | Wrong env file path, or no credentials in this runtime (e.g. a fresh container) | `ncloud config path` shows which file is read; in containers point `XDG_CONFIG_HOME` or `NEXTCLOUD_USE_ENV` at a persistent location |
| `401` | Wrong or revoked app password, or bruteforce throttling | **Do not retry**: Nextcloud throttles failed logins per source IP (each failure adds a 0.1 s x 2^n delay, 12 h window, capped at 25 s; 429 after more than 10 failures in 12 h and in the last 30 min), and agents behind the same proxy or docker host share one bucket. Run `ncloud doctor` once; check `ncloud occ -- security:bruteforce:attempts <ip>`; `security:bruteforce:reset` needs `--yes` and the user's consent |
| `412 CSRF check failed` | A manual curl without `OCS-APIRequest: true` | Add the header (the CLI does) |
| `503`, or `status.php` shows `maintenance:true` | Nextcloud maintenance mode (upgrade or backup running) | Wait; `ncloud occ -- maintenance:mode` shows the state |
| `share create` returns 429 with an empty JSON `[]` | Per-user rate limit: 20 share creations per 10 minutes | Wait 10 minutes; one share per folder, reuse existing shares |
| `/raw/*` and the raw API both return 404 **text/html** | `files_sharing_raw` is disabled (e.g. after a Nextcloud upgrade it is not compatible with; the app declares Nextcloud 32-35) | `ncloud app list --filter enabled`; `ncloud occ --yes -- app:enable files_sharing_raw` (with the user's consent). The registry survives, so sites come back once re-enabled. Temporary fallbacks: `/s/<token>` (if rawOnly is off) or `https://cloud.example.com/public.php/dav/files/<token>/<path>` (served as an attachment, not usable as a web page) |
| `filehost list` misses a site | Not under `--root` (default `/filehost`), or not a link share | `filehost --root <folder> list` (`--root` before or after the subcommand); `ncloud share list` |
| Password protection wanted on the public URL | Raw does not check share passwords | Do not use raw for access control; use `ncloud share create <path> --password <password>` (the `/s/` page) |
| Search engines do not find the page | Raw responses carry `X-Robots-Tag: noindex, nofollow` (added by core) | Expected; use other hosting for SEO |

Debug order: `ncloud doctor --deep` -> `filehost info <name>` -> `curl -sI <url>` (status and content-type) ->
browser console -> `ncloud occ -- log:tail 20`.
