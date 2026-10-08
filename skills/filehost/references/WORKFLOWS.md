# WORKFLOWS.md - common filehost workflows

The working directory is the filehost skill root. `ncloud` means the nextcloud-use CLI,
`../nextcloud-use/scripts/ncloud`. `https://cloud.example.com`, `alice`, `<share_id>` and `<token>` are
placeholders; `/filehost` is the default `FILEHOST_ROOT`.

## Contents

1. Static site (build output)
2. Single HTML report page
3. Direct links to images / JSON / PDF (chat, Markdown, programs)
4. Updating a site (same URL) and caching
5. Temporary pages (expiry), hiding the share page
6. Versioning and URL rotation
7. Batch publishing (and a short URL with relative paths)
8. Turning an existing Nextcloud folder into a raw site
9. Inventory, audit, take down
10. Verifying from outside (before handing out the URL)

---

## 1. Static site (build output)

```bash
npm run build                                                    # produces dist/ with index.html
scripts/filehost publish ./dist --name demo --prune --dry-run    # list uploads/deletions (fine before the first publish)
scripts/filehost publish ./dist --name demo --prune --yes --json # --prune without --yes is refused
```

- Relative asset paths (`assets/...`) work on `url` (`/raw/<token>/index.html`); add `--inject-base` to make the
  short URL work too.
- SPAs: use hash routing (`#/page`); history routing (`/page`) has no server rewrite and 404s.
- CDN libraries -> `--preset cdn`; iframed by other sites -> `--preset embed`.
- `.git`, `node_modules`, `.DS_Store` are always skipped; add more with `--exclude '*.map'` (repeatable).

## 2. Single HTML report page

```bash
scripts/filehost publish ./report.html --name q3-report
# -> https://cloud.example.com/raw/<token>   (single-file share: /raw/<token> is the file itself, no /index.html)
```

HTML gets the `site` preset by default; if everything is inline and no JS is needed, `--preset locked` is safer.

## 3. Direct links to images / JSON / PDF

```bash
scripts/filehost publish ./chart.png --name chart    # image/png
scripts/filehost publish ./feed.json --name feed     # application/json; for server-side code, curl
scripts/filehost publish ./paper.pdf --name paper    # application/pdf, displayed inline by browsers
```

- Automatic CSP: folders and `.html/.htm/.xhtml/.svg` files get `site`; other single files (png, json, pdf ...)
  get none (fallback), which does not affect serving images, JSON or PDF directly.
- Paste `url` straight into chat or Markdown; with no cookies and `Cache-Control: public`, link previewers and
  CDNs can cache it.
- Raw responses send no `Access-Control-Allow-Origin`: browser JS on **another origin** cannot `fetch()` this
  JSON (CORS). Raw pages on the same Nextcloud host are same-origin and can; `<img>` and server-side clients are
  unaffected.
- Several assets in one folder: after `scripts/filehost publish ./assets-dir --name assets`, each file is
  `/raw/<token>/<file>` (`scripts/filehost url assets <file>`). Without `index.html`, `/raw/<token>` answers
  **200 `application/json` `null`** (not a 404, not broken); `publish` sets `url` to the first file by path and
  verifies it; `list` does the same (`--json` adds `base` = `/raw/<token>` and `has_index: false`).
  `scripts/filehost url assets` without a path prints `.../index.html`, which such a folder lacks - pass `<file>`.

## 4. Updating a site (same URL) and caching

```bash
scripts/filehost publish ./dist --name demo --prune --yes   # reuses the share/token; --prune needs --yes
scripts/filehost verify demo --local ./dist                 # content_matches_local should be true (also for --inject-base sites)
```

- The origin updates immediately (new ETag); browsers and proxies may serve the old copy until `max-age=300`
  expires.
- When it matters: hashed asset file names (most build tools do this), `?v=<timestamp>` on HTML links, or ask an
  admin to lower `raw_cache_public_max_age`
  (`ncloud occ --yes -- config:system:set raw_cache_public_max_age --type=integer --value=30`).
- Leave out `--prune` if stale remote files should stay.

## 5. Temporary pages (expiry), hiding the share page

```bash
scripts/filehost publish ./dist --name preview --expire 2026-12-31 --raw-only
```

- `--expire` sets the share expiry date; afterwards both raw and `/s/` are 404. Expiry is enforced on raw links
  (passwords are not).
- `--raw-only` makes the `/s/<token>` share page 404 (raw only); undo with `publish ... --show-share-page`.
  Later re-publishes without a flag keep it, but after `ncloud raw disable` -> enable rawOnly is false again;
  pass `--raw-only` once more.

## 6. Versioning and URL rotation

- Versioning: `--name reports/2026-10`, `--name reports/2026-11` - independent tokens; `list` shows them all.
- Rotate the URL (old link dies, content stays):

```bash
SID_NEW=$(ncloud share create /filehost/demo --perm ro --label filehost:demo | jq -r .id)
ncloud raw enable "$SID_NEW" --preset site     # add --raw-only if wanted (a new share inherits nothing)
ncloud share delete <old_share_id> --yes        # delete exactly the old one
ncloud raw url "$SID_NEW" index.html            # the new URL
```

- Do **not** use `scripts/filehost unpublish demo --yes` to drop the old share: it deletes **all** link shares of
  the site (old and new).
- `scripts/filehost info demo` lists `share_id` and `other_shares` for the folder; once the old one is gone,
  re-publishing uses the new share.

## 7. Batch publishing

```bash
mkdir -p out
for d in sites/*/; do n=$(basename "$d"); scripts/filehost publish "$d" --name "$n" --prune --yes --json > "out/$n.json"; done
jq -r '[.name, .url] | @tsv' out/*.json
```

- OCS rate-limits **share creation to 20 per user per 10 minutes** (then 429 with an empty JSON `[]`). Publishing
  more than 20 **new** sites: split into batches and wait 10 minutes. Re-publishing existing sites does not count
  (shares are reused).
- Many assets in one folder with one share uses far less quota than one share per file.

### 7b. A short URL that keeps relative paths: go one level down

`/raw/<token>/` (trailing slash) is a 404, but **sub-folders with a trailing slash work**. Put the site one
level below the shared folder to get a short URL where relative paths work:

```bash
mkdir -p ./wrap && cp -r ./dist ./wrap/site
scripts/filehost publish ./wrap --name demo     # the share is wrap/, the site lives in wrap/site/
scripts/filehost url demo site/                 # -> https://cloud.example.com/raw/<token>/site/  (relative paths and #anchors work)
```

Trade-off: `/raw/<token>` itself has no `index.html` (200 `application/json` `null`), so the `url` printed by
`publish` / `list` is the first file in `wrap` (e.g. `site/assets/...`), not the page. Give users
`scripts/filehost url demo site/` (the trailing slash is kept).

## 8. Turning an existing Nextcloud folder into a raw site

`filehost publish` needs a local directory; for a folder already in Nextcloud use the building blocks:

```bash
ncloud raw list /Projects/site                   # existing link shares?
SID=$(ncloud share create /Projects/site --perm ro --label filehost:site | jq -r .id)
ncloud raw enable "$SID" --preset site
ncloud raw url "$SID" index.html
```

`ncloud raw enable` warns on stderr that raw is fully public (it does not block). Check the site notes
(`ncloud config notes`) before sharing anything outside `FILEHOST_ROOT`. Such a site is not under `/filehost`,
so `filehost list` does not show it (it only scans `--root`); manage it with
`scripts/filehost --root /Projects list` (`--root` works before or after the subcommand, e.g.
`scripts/filehost info site --root /Projects`).

## 9. Inventory, audit, take down

```bash
scripts/filehost list                                   # LIVE/off, share id, url, expiry
scripts/filehost list --json | jq '.[] | select(.raw_enabled)'
scripts/filehost list --json | jq '.[] | select(.has_index == false) | {name, url, base}'   # asset folders without index.html
ncloud share list --prefix /filehost/ --json            # share-level view
ncloud occ -- share:list --owner alice --type link --output=json   # admin view (--type takes names; output has id and source-path, no token)
scripts/filehost unpublish demo --yes                   # delete the share(s) (raw 404 at once), keep files
scripts/filehost unpublish demo --delete-files --yes    # also move the folder to the trash bin
ncloud trash list                                       # restore from here if needed
```

## 10. Verifying from outside (before handing out the URL)

`publish` already verifies (HTTP 200 + content-type + content hash). Double-check from another machine:

```bash
URL=https://cloud.example.com/raw/<token>/index.html
curl -sI "$URL" | grep -iE '^(HTTP|content-type|cache-control|content-security-policy)'
curl -s "$URL" | head -c 300
```

404 text/plain = raw not enabled, wrong token or missing file; 404 HTML = wrong URL shape (trailing slash);
200 `application/json` `null` = folder without `index.html`; 200 but blank page = CSP (see CSP.md).
