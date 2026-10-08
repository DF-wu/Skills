---
name: filehost
description: Publishes HTML pages, static sites, images, JSON, PDFs and other files as instant public URLs on a Nextcloud server - uploads them, creates a read-only public link share and serves raw content at /raw/<token> via the Raw Fileserver app, with CSP presets so JavaScript can run. Use when asked to publish, host, make public, get a public URL or raw link, put a static site, landing page or demo page online, or share a report as a link. Use nextcloud-use for private file management.
compatibility: Requires python3 >= 3.12 (standard library only) and the nextcloud-use skill installed in the same skills directory (or NEXTCLOUD_USE_CLI), configured for a Nextcloud server (32.0.7+ / 33.0.1+) with the files_sharing_raw app enabled. curl is optional, for manual checks.
metadata:
  clawdbot:
    requires:
      bins:
        - python3
      skills:
        - nextcloud-use
---

# filehost

Turn a local folder or a single file into a **public URL** with one command; re-running it updates the
content in place. Pipeline:

```
mkdir <FILEHOST_ROOT>/<name>/ -> find or create ONE read-only public link share -> enable the raw link (+ CSP)
  -> upload files -> verify over the public URL -> report the URL
```

It is built on the `nextcloud-use` CLI `scripts/ncloud` (WebDAV upload, OCS shares, the `files_sharing_raw`
API). `scripts/filehost` finds `nextcloud-use` in the same skills directory (or via `NEXTCLOUD_USE_CLI`).
Commands below assume the working directory is the **filehost skill root**; otherwise use
`<skill dir>/scripts/filehost`.

## When to use

- The user wants "a link": report page, demo, landing page, portfolio, any built static site (`dist/`).
- Public assets: images, SVG, JSON feeds, CSV, PDF, video, zip - to embed in chat, Markdown or other programs.
- Update a published site **without changing its URL**.
- List, inspect, re-configure or take down published sites.

**Not for**: private sharing (password, specific people) -> `nextcloud-use` (`scripts/ncloud share create`);
custom domains or CDN hosting; sites that need server-side code (PHP, SSR); pages that must be indexed by
search engines.

## Requirements and configuration

- `nextcloud-use` installed in the same skills directory as this skill, or `NEXTCLOUD_USE_CLI=/path/to/ncloud`
  (must exist when set; filehost never silently falls back to another copy).
- `nextcloud-use` configured: env file `$NEXTCLOUD_USE_ENV`, `$XDG_CONFIG_HOME/nextcloud-use/env` or
  `~/.config/nextcloud-use/env` with `NEXTCLOUD_URL`, `NEXTCLOUD_USER`, `NEXTCLOUD_APP_PASSWORD`
  (set up with `../nextcloud-use/scripts/ncloud config init --url https://cloud.example.com --user alice`).
- `FILEHOST_ROOT` - Nextcloud folder holding all sites (default `/filehost`); or `--root`, accepted before or
  after the subcommand.
- Read the private site notes first: `../nextcloud-use/scripts/ncloud config notes` (instance-specific rules,
  e.g. folders or shares never to touch).
- Check once: `../nextcloud-use/scripts/ncloud doctor --deep` - `files_sharing_raw` and `/raw route` must be OK
  (the `/raw route` row only appears with `--deep`).

## Key facts

- **Raw URLs are fully public.** The app serves by token and **does not check the share password**; share
  expiry *is* enforced. Never publish anything confidential.
- Canonical page URL: **`https://cloud.example.com/raw/<token>/index.html`**. `/raw/<token>` also serves
  `index.html`, but **`/raw/<token>/` (trailing slash) is a 404**, and on `/raw/<token>` a relative link such
  as `style.css` resolves to `/raw/style.css`. Sub-folders work with or without the slash
  (`/raw/<token>/docs/`). To make the short URL work too: `--inject-base` (inserts
  `<base href=".../index.html">`) or absolute asset paths.
- Folder **without** `index.html`: `/raw/<token>` answers **`200 application/json`, body `null`** (not a 404,
  not broken); files are still served at `/raw/<token>/<file>`. Then `publish` sets `url` to the first file
  (sorted by path) and verifies it; `short_url` is the `null` URL - never hand it out. `list` does the same
  and adds `base` (`/raw/<token>`) and `has_index` (`false`; `null` for single-file sites).
  `url <name>` without a path prints `.../index.html`, so pass `<file>` for asset folders.
- **The default CSP blocks JavaScript.** The app fallback is `sandbox; default-src 'none'; ...`: inline CSS and
  `data:` images only, no scripts, no linked CSS/images/fonts. `publish` applies the `site` preset
  automatically to folders and to `.html/.htm/.xhtml/.svg` files; other single files (png, json, pdf ...)
  keep the fallback, which does not affect direct asset serving. CDN libraries -> `--preset cdn`;
  embedding in other sites' iframes -> `--preset embed`.
- Only members of `csp_editor_group` (app config, default `admin`) can set a CSP; for others the value is
  silently ignored. CSP changes take effect immediately.
- **Caching**: the origin serves new content right after a re-publish (new ETag), but browsers and proxies may
  keep the old copy for up to `Cache-Control: max-age=300` (5 minutes). Use `?v=2`, or an admin can lower
  `raw_cache_public_max_age` via occ.
- Re-publishing the same `--name` **reuses the same share and token** (same URL). Only `--prune` deletes remote
  files missing locally; it needs `--yes` unless `--dry-run`.
- `--raw-only` makes the `/s/<token>` share page 404 (raw only). Without a flag, re-publishing keeps the current
  rawOnly - but after `../nextcloud-use/scripts/ncloud raw disable` and a re-enable, rawOnly is back to false
  (the CSP is kept); pass `--raw-only` again.
- `unpublish` deletes the share(s) -> the token is 404 immediately; `--delete-files` also moves the folder to
  the trash bin.
- MIME type comes from the file extension (`.html` text/html, `.js` application/javascript, `.css` text/css,
  `.svg` image/svg+xml, `.json` application/json); files without an extension are sniffed. Responses carry
  `X-Content-Type-Options: nosniff`, so extensions must be right.
- Responses carry `X-Robots-Tag: noindex, nofollow`: raw pages are **not indexed** by search engines.
- Creating shares is rate-limited per user: **20 per 10 minutes** (then 429 with an empty `[]`). Batch new sites.

## Quick start

```bash
scripts/filehost publish ./dist --name demo                     # folder -> site (CSP preset: site)
scripts/filehost publish ./chart.png                            # single file -> direct URL (name = file stem)
scripts/filehost publish ./dist --name demo --prune --dry-run   # preview uploads and deletions
scripts/filehost publish ./dist --name demo --prune --yes       # update (same URL), drop stale remote files
scripts/filehost list                                           # all published sites + state
scripts/filehost url demo assets/app.js                         # public URL of a file (percent-encoded)
scripts/filehost url demo docs/                                 # sub-folder: trailing slash kept
scripts/filehost verify demo --local ./dist                     # 200? content-type? CSP? same bytes as local?
scripts/filehost csp demo --preset cdn                          # change the CSP
scripts/filehost unpublish demo --delete-files --yes            # take down (URL is 404 at once)
scripts/filehost --help
scripts/filehost publish --help
```

`publish --json` prints `url`, `short_url`, `share_page`, `share_id`, `token`, `csp`, `uploaded`, `verify`.

## Publish checklist (plan -> execute -> verify)

1. **Confirm it may be public**: no passwords, keys, personal data; nothing meant for one person only (that is
   `ncloud share create <path> --password <password>` in nextcloud-use).
2. **Pick a name**: lowercase letters, digits and `-`; `/` nests (`reports/2026-10`). Same name = update.
3. **Pick a CSP**: plain HTML / same-origin JS -> `site` (default for folders and HTML-like files); CDN
   libraries -> `cdn`; iframe embedding by other sites -> `embed`; other single assets need nothing.
4. **Dry run**: `publish ... --dry-run` lists uploads (with `--prune` also deletions; works before the remote
   folder exists).
5. **Publish**: add `--raw-only`, `--expire YYYY-MM-DD`, `--prune --yes` or `--inject-base` as needed. Many
   **new** sites at once: stay under 20 share creations per 10 minutes.
6. **Verify**: `publish` probes the public URL (`verify.status` 200, `content_matches_local` true; for a folder
   without `index.html` it checks the file `url` points at). From another machine: `curl -sI <url>`.
7. **Report**: give `url` (the `index.html` form); for folder sites say this is the URL to use when assets use
   relative paths; for asset folders give `/raw/<token>/<file>` URLs (`scripts/filehost url <name> <file>`),
   never the short URL; mention the 5-minute cache and how to update or take down.

## CSP presets

Exact values: `CSP_PRESETS` in `../nextcloud-use/scripts/ncloud` (print with `scripts/filehost presets`).

| preset | Allows | Use for |
|---|---|---|
| `locked` (= app fallback) | inline CSS, `data:` images; **no JS** | plain text pages, untrusted content |
| `site` (default) | same-origin script/style/img/font/media + inline script/style; `connect-src 'self'`; no iframe embedding | static sites, report pages |
| `cdn` | `site` + any `https:` script/style/img/font/media/connect/frame, plus `'unsafe-eval'` | pages using CDN libraries or external APIs |
| `embed` | identical to `cdn` (incl. `'unsafe-eval'`) except `frame-ancestors *` | pages embedded by other sites |
| `asset` | `default-src 'none'; img-src 'self' data:; ...; sandbox` | a single image/media file (never automatic; `--preset asset`) |

Custom: `--csp "default-src 'self'; img-src https:"`. Per-share CSP is sent as is - **directive names are not
validated**, so a typo fails silently; check the header with `verify`. Priority chain: `references/CSP.md`.

## Commands

```bash
# publish / update
scripts/filehost publish ./site --name blog --preset cdn --raw-only
scripts/filehost publish ./site --name blog --prune --yes --inject-base
scripts/filehost publish ./notes.html --name notes            # single HTML: /raw/<token> is the page itself
scripts/filehost publish ./feed.json --name feed --expire 2026-12-31
scripts/filehost publish ./site --name blog --show-share-page # undo --raw-only
# inspect
scripts/filehost list --json                  # url, base, has_index, raw_enabled, raw_only, csp per site
scripts/filehost --root /Projects list        # another root (--root before or after the subcommand)
scripts/filehost info blog                    # share, raw state, file count and bytes (single file: files=1)
scripts/filehost url blog
scripts/filehost verify blog --local ./site
scripts/filehost presets
# change / take down
scripts/filehost csp blog --csp "default-src 'self'"
scripts/filehost unpublish blog --yes         # delete the share(s) only; files stay
scripts/filehost unpublish blog --delete-files --yes
```

Building blocks (manual work or debugging):

```bash
../nextcloud-use/scripts/ncloud upload-dir ./site /filehost/blog --prune --yes  # --prune needs --yes (or --dry-run)
../nextcloud-use/scripts/ncloud share create /filehost/blog --perm ro --label filehost:blog
../nextcloud-use/scripts/ncloud raw enable <share_id> --preset site --raw-only   # stderr warns raw is public
../nextcloud-use/scripts/ncloud raw get <share_id>
curl -sI https://cloud.example.com/raw/<token>/index.html
```

## Report template

```
Published: <name>
  URL        https://cloud.example.com/raw/<token>/index.html
  Short URL  https://cloud.example.com/raw/<token>   (only if the page uses absolute paths or --inject-base)
  Share      id=<share_id>  raw_only=<bool>  csp=<preset>  expires=<date|none>
  Verified   HTTP 200 text/html, content matches local
  Update:    re-run the same publish (same URL; caches may serve the old copy for up to 5 minutes)
  Take down: scripts/filehost unpublish <name> --yes
```

## Safety rules

- Never publish passwords, tokens, personal data or content without the rights to it; ask when unsure.
  Raw links are public and ignore share passwords.
- Only touch folders and shares under `FILEHOST_ROOT`; anything else goes through `nextcloud-use`, after
  confirmation, and respecting the site notes.
- `unpublish`, `--prune` and `--delete-files` require `--yes` (the CLI refuses otherwise) and an explicit user
  request; run `list` / `--dry-run` first.
- Do not change system-level `raw_csp`, `allowed_raw_tokens` or `raw_cache_*` on your own (occ + user consent).
- Never retry a 401: failed logins are throttled per source IP, and agents behind the same proxy or docker host
  share one bruteforce bucket.
- Report URLs and share ids only; never paste the app password, the env file or any credential.

## References

- `references/RAW_FILESERVER.md` - `files_sharing_raw` routes, API, allowlist model, headers, cache, URL-shape
  matrix, rawOnly/password/expiry, system config keys, private `/raw/u/`. Read for anything beyond
  publish/list/verify or for occ-level tuning.
- `references/CSP.md` - CSP priority chain, fallback policy, presets, directive filtering, recipes, system
  `raw_csp`. Read when a page is blank, JS does not run, or a custom policy is needed.
- `references/WORKFLOWS.md` - static sites, single pages, assets, updates and caching, temporary pages,
  versioning and URL rotation, batches, existing Nextcloud folders, audits, outside verification.
- `references/TROUBLESHOOTING.md` - symptom -> cause -> fix table. Read when `verify` fails.

## Maintenance

1. After a `files_sharing_raw` upgrade: `../nextcloud-use/scripts/ncloud occ -- app:list --output=json` and
   `../nextcloud-use/scripts/ncloud occ -- router:list files_sharing_raw`; update
   `references/RAW_FILESERVER.md` and "Key facts" if behaviour changed.
2. After a Nextcloud upgrade: run `tests/`, a `publish --dry-run`, then a real `publish` to `_selftest` and
   `unpublish _selftest --delete-files --yes`.
3. If the `ncloud` module interface changes (`raw_set`, `raw_get`, `raw_list_for_path`, `upload_dir`,
   `walk_local`, `list_tree`, `SHARE_API`, `CSP_PRESETS`), update `scripts/filehost`.
