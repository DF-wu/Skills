# API_WEBDAV.md — WebDAV file operations

Reference for Nextcloud's WebDAV API. Behaviour was observed on Nextcloud 33 (AIO) unless marked
**UNVERIFIED** (derived from server source or official docs, not run live — usually because it writes).
Each section gives the `scripts/ncloud` subcommand first, then the raw HTTP (method, path, headers, body
template, trimmed response). Status-code fixes are in `TROUBLESHOOTING.md`; instance-specific rules (folders
never to scan, shares never to touch) live in the private site notes (`scripts/ncloud config notes`,
see `SITE_NOTES.md`) — read them before acting.

Placeholders: base URL `https://cloud.example.com` (`$NC`), user `alice` (`$U`), `<fileid>`, `<token>`,
`<etag>`, `<instanceid>`. Every id, etag and path below is illustrative.

## Contents

1. Conventions (endpoints, auth, URL encoding, namespaces, parsing, folder test)
2. PROPFIND (Depth, property matrix, permission letters, pagination)
3. MKCOL / PUT (and `upload-dir`)
4. GET / HEAD / folder zip (and `download-dir`)
5. MOVE / COPY / DELETE
6. Chunked upload v2
7. SEARCH
8. REPORT (favorites, system tags) and PROPPATCH
9. Trash bin
10. Versions
11. Comments and tags
12. fileid <-> path
13. Team folders, external storage, public share DAV
14. Error codes and brute-force protection
15. Decision rules

---

## 1. Conventions

### 1.1 Endpoint tree

| Purpose | Path (after `$NC`) | Methods |
|---|---|---|
| DAV root: OPTIONS, **SEARCH** | `/remote.php/dav/` | OPTIONS, SEARCH (`dav: 1, 3, extended-mkcol, nc-paginate, nextcloud-checksum-update, …`; no class 2, so no LOCK/UNLOCK) |
| User file tree (legacy alias `/remote.php/webdav/<path>`) | `/remote.php/dav/files/<user>/<path>` | PROPFIND, GET, HEAD, PUT, MKCOL, MOVE, COPY, DELETE, PROPPATCH, REPORT, PATCH (SEARCH here -> 501) |
| Chunked upload | `/remote.php/dav/uploads/<user>/<upload-id>/` | MKCOL, PUT, MOVE, DELETE (PROPFIND on `/uploads/<user>/` -> 405) |
| Trash bin / versions | `/remote.php/dav/trashbin/<user>/trash/`, `…/restore/`; `/remote.php/dav/versions/<user>/versions/<fileid>/`, `…/restore/` | PROPFIND, GET, MOVE, DELETE (versions also PROPPATCH) |
| Comments / system tags | `/remote.php/dav/comments/files/<fileid>/`; `/remote.php/dav/systemtags/`, `…/systemtags-relations/files/<fileid>/`, `…/systemtags-assigned/files/` | PROPFIND, REPORT, POST, PUT, PROPPATCH, DELETE |
| fileid redirect | `/f/<fileid>`, `/index.php/f/<fileid>` | GET/HEAD -> 303 |
| Thumbnail (not DAV) | `/index.php/core/preview?fileId=<fileid>&x=256&y=256&a=1` | GET, Basic auth only |
| Public share DAV | `/public.php/dav/files/<token>/<path>` | as the file tree, limited by the share's permissions (§13.1) |

### 1.2 Basic auth and shell variables

```bash
set -a; . "${NEXTCLOUD_USE_ENV:-${XDG_CONFIG_HOME:-$HOME/.config}/nextcloud-use/env}"; set +a   # same env file as the CLI
NC=$NEXTCLOUD_URL; U=$NEXTCLOUD_USER; AUTH="$U:$NEXTCLOUD_APP_PASSWORD"                         # all curl below: -u "$AUTH"
```

- `scripts/ncloud config path` prints the env file the CLI uses. `curl -u` puts the password on the command line
  (visible in `ps` on shared hosts); prefer `scripts/ncloud call` there.
- Use an **app password** only. A 2FA account using its login password gets 401 `2FA challenge not passed.`;
  an account with password login disabled gets 401 `PasswordLoginForbidden`. Never retry a 401 (§14).
- DAV needs no `OCS-APIRequest` header or CSRF token. `scripts/ncloud call` always sends `OCS-APIRequest: true`
  (harmless on DAV); `--no-ocs` only stops it from appending `format=json` to `/ocs/` URLs, so it is a no-op for
  DAV paths. `call` sends credentials only to the `NEXTCLOUD_URL` origin (other hosts need `--no-auth`, which
  sends no Authorization), and `DELETE` needs `--yes` (`API_OCS.md`).
- Every Basic-auth request is a fresh login (the response carries several `Set-Cookie` headers; ignore them).
  Useful response headers: `x-request-id` (find it with `scripts/ncloud occ -- log:tail 50 --raw | jq 'select(.reqId=="…")'`),
  `etag` / `oc-etag`, `oc-fileid`.
- Request `Content-Type`: `application/xml; charset=utf-8` for PROPFIND/REPORT/PROPPATCH; SEARCH is documented
  as `text/xml` (`application/xml` also returns 207). Success is `207 Multi-Status`; errors are `d:error` XML (§14).
  `Prefer: return=minimal` drops the 404 propstat blocks and returns only the 200 block (response has `vary: Brief,Prefer`).

### 1.3 Percent-encode the path segment by segment

The CLI's `quote_path()` applies `urllib.parse.quote(seg, safe="")` to each segment and keeps `/`. By hand:

```bash
enc() { python3 -c 'import sys,urllib.parse as u; print("/".join(u.quote(s, safe="") for s in sys.argv[1].split("/")))' "$1"; }
enc "Reports/Q1 #draft/Résumé 2026.pdf"
# Reports/Q1%20%23draft/R%C3%A9sum%C3%A9%202026.pdf   (space %20, # %23, ? %3F, % %25, + %2B)
curl -sS -u "$AUTH" -X PROPFIND -H 'Depth: 0' "$NC/remote.php/dav/files/$U/$(enc 'Reports/Q1 #draft')/"
```

- Raw UTF-8 in a curl URL usually works, but **an unencoded `#` is treated as a fragment and the path is cut**:
  `…/files/alice/#archive/` silently returns the 207 for `/files/alice/` (the wrong resource). Always encode;
  the `Destination:` header (MOVE/COPY) must also be a percent-encoded absolute URL.
- **SEARCH is the opposite: `<d:scope><d:href>` takes the raw, unencoded path** (`/files/alice/Travel docs` -> 207;
  the encoded form -> 404).
- Response `d:href` values are percent-encoded (SEARCH uses lowercase hex); `urllib.parse.unquote` them before
  comparing. `d:displayname` is raw UTF-8.
- Forbidden names (capabilities `files.*`): `.htaccess`, the characters `\` and `/`, the extensions `.filepart`
  and `.part` -> 400 `InvalidPath` or 403.

### 1.4 XML namespaces and minimal parsing

Always declare `xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns"` in request
bodies (add `xmlns:ocs="http://open-collaboration-services.org/ns"` for share-permission properties). Responses
also declare `xmlns:s="http://sabredav.org/ns"`, and prefixes can change (e.g. `x1:share-permissions`):
**parse by namespace URI, never by prefix.** The CLI's `parse_multistatus()` does this; a minimal version:

```python
import xml.etree.ElementTree as ET
from urllib.parse import unquote
NS = {"d": "DAV:", "oc": "http://owncloud.org/ns", "nc": "http://nextcloud.org/ns"}
def entries(xml_bytes):
    for r in ET.fromstring(xml_bytes).findall("d:response", NS):
        href = unquote(r.findtext("d:href", namespaces=NS))
        ok = next((ps.find("d:prop", NS) for ps in r.findall("d:propstat", NS)
                   if "200" in ps.findtext("d:status", namespaces=NS)), None)   # read only the 200 block
        if ok is None: continue
        yield {"href": href,
               "is_dir": ok.find("d:resourcetype/d:collection", NS) is not None,
               "fileid": ok.findtext("oc:fileid", namespaces=NS),
               "size": ok.findtext("oc:size", namespaces=NS),
               "etag": (ok.findtext("d:getetag", namespaces=NS) or "").strip('"')}
```

Each `d:response` has several `d:propstat` blocks: the `HTTP/1.1 200 OK` block holds values; the
`404 Not Found` block lists properties this node does not have (e.g. `d:getcontentlength` on a folder). That is
not an error.

### 1.5 Folder or file

The only reliable test is `<d:collection/>` inside `d:resourcetype`. A trailing `/` on the href, a missing
`d:getcontenttype` (PROPFIND) or `httpd/unix-directory` (SEARCH) are only hints. `scripts/ncloud ls --json`
exposes this as `is_dir`.

---

## 2. PROPFIND

```bash
scripts/ncloud ls /Photos --depth 1 -l --json      # list a folder; the CLI drops the first entry (the folder itself)
scripts/ncloud ls /Projects/small --depth infinity # works on NC 33 (§2.1); only for small subtrees
scripts/ncloud stat /Documents --json              # Depth 0: fileid, etag, permissions, share_types, ...
scripts/ncloud tree /Photos/2026 -l                # recursive, one Depth 1 request per folder (safe on big mounts)
scripts/ncloud call PROPFIND /remote.php/dav/files/alice/Photos -H 'Depth: 1' --body-file props.xml -i
```

Default properties of `ls`/`stat` (`Client.PROPS`): `d:resourcetype d:getcontentlength d:getcontenttype d:getetag
d:getlastmodified oc:fileid oc:id oc:size oc:permissions oc:share-types oc:favorite oc:owner-id oc:checksums
nc:has-preview nc:is-mount-root oc:comments-unread`, with `Depth: <n>` and `Content-Type: application/xml`.

```bash
cat > props.xml <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns">
  <d:prop><d:resourcetype/><d:getlastmodified/><d:getetag/><d:getcontenttype/><d:getcontentlength/>
    <oc:fileid/><oc:id/><oc:size/><oc:permissions/><oc:share-types/><oc:favorite/><oc:owner-id/>
    <nc:has-preview/><nc:is-mount-root/><nc:mount-type/><nc:system-tags/><oc:checksums/></d:prop>
</d:propfind>
XML
curl -sS -u "$AUTH" -X PROPFIND -H 'Depth: 1' -H 'Prefer: return=minimal' \
  -H 'Content-Type: application/xml; charset=utf-8' --data-binary @props.xml "$NC/remote.php/dav/files/$U/Photos/"
```

```xml
<d:multistatus xmlns:d="DAV:" xmlns:s="http://sabredav.org/ns" xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns">
 <d:response><d:href>/remote.php/dav/files/alice/Photos/notes.md</d:href>
  <d:propstat><d:prop><d:resourcetype/><oc:fileid>12345</oc:fileid><oc:size>0</oc:size>
   <oc:permissions>RGDNVW</oc:permissions><nc:mount-type></nc:mount-type><nc:system-tags/></d:prop>
  <d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response></d:multistatus>
```

Without a body (or with `<d:allprop/>`) you get only Sabre's default properties — always list the properties.

### 2.1 Depth

- `Depth: 0` = the node itself; `Depth: 1` = node plus direct children (the first `d:response` is the folder
  itself — skip it); a missing header counts as 1.
- **`Depth: infinity` works on Nextcloud 33** (a multi-level test folder returned every descendant):
  `apps/dav/lib/Connector/Sabre/Server.php` sets `enablePropfindDepthInfinity = true` unconditionally, and NC 33
  has no config switch for it (`dav.propfind.depth_infinity` is ownCloud's key). If a future version turns it off,
  Sabre silently answers as Depth 1 instead of failing.
- Never send infinity to the home root or to a large mount (multi-TB external storage, big photo libraries): the
  whole XML is built in PHP memory. Use SEARCH (§7), `scripts/ncloud tree`, or paginated Depth 1 instead.

### 2.2 Property matrix (404 = this node does not have the property)

| Property | Folder | File | Notes |
|---|---|---|---|
| `d:resourcetype` | `<d:collection/>` | empty | the only reliable type test |
| `d:getlastmodified` | RFC 1123 | RFC 1123 | `Thu, 01 Jan 2026 12:00:00 GMT` |
| `d:getetag` | `"<etag>"` | `"<etag>"` | quoted; a parent's etag changes when any descendant changes |
| `d:getcontenttype` | 404 | `text/markdown` | folders show `httpd/unix-directory` in SEARCH results |
| `d:getcontentlength` | 404 | bytes | use `oc:size` for folders |
| `d:creationdate` / `nc:creation_time` | epoch / `0` | same | 0 = unknown |
| `d:quota-available-bytes` | `-3` on mounts | – | `-1` not computed, `-2` unknown, `-3` unlimited |
| `oc:fileid` | numeric | numeric | the numeric id used everywhere |
| `oc:id` | `00012345<instanceid>` | same | fileid zero-padded to 8 digits + instance id; equals the `OC-FileId` header |
| `oc:size` | bytes incl. descendants | bytes | |
| `oc:permissions` | `RMGNVCK` | `RGDNVW` | §2.3 |
| `oc:share-types` | `<oc:share-type>3</oc:share-type>` | empty | 0 user, 1 group, 3 link, 4 email, 6 federated, 7 circle/team, 10 Talk, 12 Deck |
| `oc:favorite` | 0/1 | 0/1 | writable with PROPPATCH (§8) |
| `oc:owner-id`, `oc:comments-count` / `oc:comments-unread` / `oc:comments-href` | `alice`, 0 / 0 / `/remote.php/dav/comments/files/<fileid>` | same | |
| `oc:checksums` | 404 | 404 unless uploaded with `OC-Checksum` or recalculated with PATCH (§3.1) | `<oc:checksum>SHA1:… MD5:… ADLER32:…</oc:checksum>`, space separated |
| `nc:has-preview` / `nc:is-mount-root` / `nc:mount-type` | `false` / true or false / `external`, `group`, `shared` or empty | true or false / `false` / empty | §13 |
| `nc:rich-workspace`, `nc:contained-folder-count` / `nc:contained-file-count` | `""`, numbers | – | folder Readme.md (Text app); child counts |
| `nc:system-tags` | `<nc:system-tags/>` | same | NC 27+; children `<nc:system-tag oc:id=".." oc:can-assign="..">name</nc:system-tag>` (child shape UNVERIFIED) |
| `nc:sharees`, `nc:share-attributes`, `nc:hidden`, `nc:reminder-due-date`, `oc:tags` | yes | yes | `oc:tags` = legacy personal tags; `oc:systemtag` and `oc:downloadURL` are 404 (the former is a REPORT rule name, not a property) |
| `nc:acl-enabled`, `nc:acl-can-manage`, `nc:acl-list`, `nc:group-folder-id` | team folders only | | §13 |
| `ocs:share-permissions` | `31` | | 1 read, 2 update, 4 create, 8 delete, 16 share |

### 2.3 `oc:permissions` letters

`S` shared with me, `R` re-shareable, `M` mount point, `G` readable, `D` deletable, `N` renamable, `V` movable,
`W` writable (files), `C` can create files inside, `K` can create folders inside.

Trap: `N`, `V` (and in practice `D`) are computed **relative to the parent**. The same mount root shows `RMGCK` in
its parent's Depth 1 listing and `RMGNVCK` in its own Depth 0 response. To answer "can I rename / move / delete
this item", read the parent listing; to answer "what can I do inside it", read Depth 0.

### 2.4 Pagination (`nc-paginate`, NC 31+; PROPFIND, SEARCH and REPORT)

```bash
curl -sS -D hdr.txt -u "$AUTH" -X PROPFIND -H 'Depth: 1' -H 'X-NC-Paginate: true' -H 'X-NC-Paginate-Count: 500' --data-binary @props.xml "$NC/remote.php/dav/files/$U/" > page1.xml
TOK=$(grep -i '^x-nc-paginate-token' hdr.txt | awk '{print $2}' | tr -d '\r')   # also x-nc-paginate-total
curl -sS -u "$AUTH" -X PROPFIND -H 'Depth: 1' -H 'X-NC-Paginate: true' -H "X-NC-Paginate-Token: $TOK" -H 'X-NC-Paginate-Offset: 500' -H 'X-NC-Paginate-Count: 500' "$NC/remote.php/dav/files/$U/" > page2.xml
```

The full result of the first request is cached server-side for 1 hour; later pages ignore their body (the property
list comes from page 1). The folder itself counts as item 0 of the total. NC 33 returns token/total even when one
page suffices; other versions may omit them — treat "no token/total" as done, otherwise stop when
`offset + count >= total`. The CLI does not paginate.

---

## 3. MKCOL / PUT

```bash
scripts/ncloud mkdir -p /Projects/2026/q4            # MKCOL per segment; 201 or 405 (exists) both count as success
scripts/ncloud put ./a.pdf /Documents/a.pdf          # sends X-NC-WebDAV-Auto-Mkcol: 1, X-OC-Mtime (--no-mtime to skip), guessed Content-Type
echo "text" | scripts/ncloud put - /Notes/today.md   # from stdin; local files >= 64 MiB switch to chunked upload (§6)
scripts/ncloud upload-dir ./dist /Projects/site --exclude '*.map' --prune --dry-run   # preview uploads and deletions
scripts/ncloud upload-dir ./dist /Projects/site --exclude '*.map' --prune --yes       # really delete extra remote files (after the user agrees)
```

- `put` prints `created|updated <path> fileid=<oc-fileid> etag=<oc-etag>`. Below the chunk threshold the CLI reads
  the file into memory and sends one PUT.
- `upload-dir`: MKCOL the target with parents, MKCOL every subfolder (201/405), `put` every file (chunked when large),
  then print JSON counts (`dirs`, `files`, `bytes`, `pruned`). Default excludes: `.git`, `.DS_Store`, `Thumbs.db`,
  `node_modules`; `--exclude` adds fnmatch patterns (matched against the relative path and the file name). To
  skip a folder pass `build`, `build/*` and `*/build/*`: a bare name only skips the folder entry itself, its files
  still match by path and get uploaded.
- `--prune` lists the remote tree and DELETEs remote files that are not in the local tree (they go to the trash bin).
  **It needs `--yes` unless `--dry-run`.** `--prune --dry-run` on a remote folder that does not exist yet treats it
  as empty (preview a first publish without a 404); `--dry-run` uploads and deletes nothing.

```bash
curl -sS -u "$AUTH" -X MKCOL "$NC/remote.php/dav/files/$U/$(enc 'New folder')/"   # 201; 405 exists; 409 parent missing; 403 no K
curl -sS -D - -o /dev/null -u "$AUTH" -T ./local.bin \
  -H "X-OC-Mtime: $(stat -c %Y ./local.bin)" -H 'X-NC-WebDAV-Auto-Mkcol: 1' \
  "$NC/remote.php/dav/files/$U/dir/sub/local.bin"
# HTTP/1.1 201 Created (204 when overwriting)  oc-fileid: 00012345<instanceid>  oc-etag: "<etag>"  x-oc-mtime: accepted
```

- Use `-T file` (streams, sends `Content-Length`). Avoid `--data-binary @big` (whole file in RAM) and chunked
  transfer-encoding: with `Content-Length`, Nextcloud compares the bytes written and answers **400**
  `Expected filesize of X bytes but read … Y bytes` on a mismatch (not 413).
- `X-OC-Mtime: <unix seconds>` (integer) sets the mtime, `X-OC-CTime` the creation time; acceptance is confirmed by
  `X-OC-Mtime: accepted`.
- `X-NC-WebDAV-Auto-Mkcol: 1` creates missing parent folders. The server's `UploadAutoMkcolPlugin` matches this
  hyphenated spelling; the docs' `X-NC-WebDAV-AutoMkcol` is wrong — trust the source.
- Preconditions: `If-Match: "<etag>"` mismatch -> 412 (optimistic locking); `If-Match: *` on a missing file -> 412;
  `If-None-Match: *` on an existing file -> 412 (create-only). Send the etag with its quotes. Overwriting creates a
  version (§10). PUT to an existing **folder** URL -> 409 `PUT is not allowed on non-files.`
- Size limits: the largest single PUT is the smallest of the reverse proxy body limit (e.g. nginx
  `client_max_body_size`), Apache `LimitRequestBody` and PHP `upload_max_filesize`/`post_max_size`; long uploads
  also need generous proxy read timeouts and PHP `max_execution_time` (AIO: `NEXTCLOUD_UPLOAD_LIMIT`,
  `NEXTCLOUD_MAX_TIME`). An HTML 413 comes from a proxy. Above 64 MiB prefer chunked upload (§6) anyway.
  507 = quota full; 403 = read-only mount (no `W`/`C`); 423 = target locked (back off and retry).

### 3.1 Checksums

- `OC-Checksum: SHA1:<hex>` (also `MD5:`, `SHA256:`, `ADLER32:`, several space separated) is **stored as is** in
  `oc:checksums`; the server does not verify it — treat it as self-declared metadata.
- `X-Hash: md5|sha1|sha256|all` makes the server hash while receiving and answer `X-Hash-MD5` / `X-Hash-SHA1` /
  `X-Hash-SHA256` headers (source `File.php`; UNVERIFIED).
- After the fact: `PATCH` with `X-Recalculate-Hash: sha256` -> 204 + `OC-Checksum: SHA256:<hex>`, also written to
  `oc:checksums`, replacing any multi-algorithm string (this is OPTIONS' `nextcloud-checksum-update`; UNVERIFIED,
  writes the file cache).

```bash
scripts/ncloud call PATCH /remote.php/dav/files/alice/dir/sub/local.bin -H 'X-Recalculate-Hash: sha256' -i
curl -sS -D - -o /dev/null -u "$AUTH" -X PATCH -H 'X-Recalculate-Hash: sha256' "$NC/remote.php/dav/files/$U/dir/sub/local.bin"
```

---

## 4. GET / HEAD / folder zip

```bash
scripts/ncloud get /notes.md -                   # to stdout (held in memory)
scripts/ncloud get /Documents/a.pdf ./a.pdf      # streamed to a file; local parent folders are created
scripts/ncloud download-dir /Photos/2026 ./photos2026
scripts/ncloud call HEAD /remote.php/dav/files/alice/notes.md -i
```

- `download-dir` walks the remote tree (one Depth 1 PROPFIND per folder), creates local folders and GETs every
  file, overwriting existing local files. It **refuses any server-returned path that would land outside the target
  folder** (`..` segments or a path resolving elsewhere) and aborts. It never deletes local files.

```bash
curl -sS -u "$AUTH" -o out.pdf "$NC/remote.php/dav/files/$U/$(enc 'Travel docs/x.pdf')"   # 200; content-disposition: attachment; filename*=UTF-8''…
curl -sS -I -u "$AUTH" "$NC/remote.php/dav/files/$U/notes.md"                              # HEAD: etag, oc-etag, last-modified, content-length
curl -sS -u "$AUTH" -H 'Range: bytes=0-4' "$NC/remote.php/dav/files/$U/f.txt" -o part      # 206, content-range: bytes 0-4/13
curl -sS -u "$AUTH" -H 'If-None-Match: "<etag>"' "$NC/remote.php/dav/files/$U/notes.md"    # 304 when unchanged
curl -sS -u "$AUTH" -H 'Accept: application/zip' -o folder.zip "$NC/remote.php/dav/files/$U/Photos/2026/"   # streamed zip
```

- **GET on a folder without `Accept` returns `200 text/html`** ("This is the WebDAV interface…"): a 200 that is not
  your data. Check `d:resourcetype` first, or check `content-type`.
- zip/tar: `Accept: application/zip` or `application/x-tar`; limit to some children with repeated
  `X-NC-Files: <name>` headers or `?accept=zip&files=["a.txt","b.png"]`; an unreadable child -> 403; temporarily
  unavailable -> 503.
- Thumbnails (not DAV; Basic auth only, no `OCS-APIRequest`):
  `GET $NC/index.php/core/preview?fileId=<fileid>&x=256&y=256&a=1` -> `200 image/png`; unknown id -> 404.

---

## 5. MOVE / COPY / DELETE

```bash
scripts/ncloud mv /Inbox/a.txt /Archive/a.txt --overwrite   # default Overwrite: F; --overwrite sends T
scripts/ncloud cp /Documents/a.pdf /Backup/a.pdf
scripts/ncloud rm /Inbox/old --yes                           # DELETE -> trash bin; needs --yes
```

```bash
curl -sS -u "$AUTH" -X MOVE -H "Destination: $NC/remote.php/dav/files/$U/$(enc 'Archive/Report 2026.pdf')" -H 'Overwrite: F' \
  "$NC/remote.php/dav/files/$U/Inbox/report.pdf"            # 201 new target / 204 overwritten
curl -sS -u "$AUTH" -X COPY -H "Destination: $NC/remote.php/dav/files/$U/Backup/report.pdf" "$NC/remote.php/dav/files/$U/Inbox/report.pdf"
curl -sS -u "$AUTH" -X DELETE "$NC/remote.php/dav/files/$U/Inbox/old/"   # 204; folders are recursive
```

- `Destination` is required (missing -> 400 `The destination header was not supplied`): a full URL or absolute
  path, percent-encoded, on the same DAV server. Rename = MOVE. `Overwrite: T` (the protocol default) overwrites;
  `Overwrite: F` with an existing target -> 412; missing target parent -> 409.
- MOVE across mounts (team folder, external storage) is a server-side copy + delete: slow for big trees and may
  produce 423/507. A COPY result has a new fileid and etag.
- DELETE moves the item to the trash bin (kept per `trashbin_retention_obligation`, default `auto`: at least
  30 days, purged earlier only when space is needed). A mount root has no `D` in its parent listing -> 403.
- **DELETE on an external storage mount also goes to the user's home trash bin, copying the bytes into the
  user's `files_trashbin` in the data directory** (`files_trashbin/lib/Storage.php` wraps every mount; no size cap
  unless `trashbin:size` is set). Deleting large files on a multi-TB external mount is slow and fills the home
  storage. UNVERIFIED (no write test); try a small file first. Team folders use their own trash backend (§9).

---

## 6. Chunked upload v2

CLI: `put` and `upload-dir` switch to `put_file_chunked()` for local files **>= 64 MiB**
(`NEXTCLOUD_CHUNK_THRESHOLD_MB`), with **20 MiB** chunks (`NEXTCLOUD_CHUNK_SIZE_MB`; matches the capability
`files.chunked_upload.max_size = 20971520`). These two variables are read from the **process environment only**
(not from the env file). Upload id `ncloud-<unix>-<pid>`, chunk names `00001`, `00002`, …; MKCOL and every PUT carry
`Destination` + `OC-Total-Length`; the final `MOVE .file` carries `Destination`, `Overwrite: T`, `OC-Total-Length`
and `X-OC-Mtime`; on any failure the CLI DELETEs the upload folder. Chunks are sent sequentially (the capability
suggests `max_parallel_count: 5` to web clients).

```bash
DEST="$NC/remote.php/dav/files/$U/$(enc 'Videos/video.mkv')"
UP="$NC/remote.php/dav/uploads/$U/$(uuidgen)"; SIZE=$(stat -c %s ./video.mkv)
curl -sS -u "$AUTH" -X MKCOL -H "Destination: $DEST" -H "OC-Total-Length: $SIZE" "$UP"       # 201
split -b 20M -d -a 5 --numeric-suffixes=1 ./video.mkv chunk_                                    # chunk_00001 …
for c in chunk_*; do n=${c#chunk_}
  curl -sS -u "$AUTH" -T "$c" -H "Destination: $DEST" -H "OC-Total-Length: $SIZE" "$UP/$n"; done   # 201 each
curl -sS -u "$AUTH" -X MOVE -H "Destination: $DEST" -H 'Overwrite: T' -H "OC-Total-Length: $SIZE" \
  -H "X-OC-Mtime: $(stat -c %Y ./video.mkv)" "$UP/.file"                                        # 201/204 -> assembled
curl -sS -u "$AUTH" -X DELETE "$UP/"                                                            # abort (when giving up)
```

- Capabilities: `dav.chunking = "1.0"`, `files.bigfilechunking = true`,
  `files.chunked_upload = {max_size: 20971520, max_parallel_count: 5}` (hints for the web client, not server limits).
- **Primary storage matters.** With local primary storage (no S3 `objectstore`), `ChunkingV2Plugin::beforePut()`'s
  `checkPrerequisites()` throws `StorageInvalidException` and the server falls back to the v1 flow (chunks stored in
  the upload folder, concatenated in natural name order on MOVE). The documented rule "chunk names must be numbers
  1…10000" is then not enforced, but keep that naming (S3 primary storage enforces it, plus S3's 5 MiB minimum chunk
  size except for the last chunk).
- Send `Destination` on MKCOL, every PUT and the final MOVE (required by v2, harmless in v1). `OC-Total-Length` is
  optional: on PUT it lets the server reject early with 507 when the quota is too small; on MOVE it is compared with
  the assembled size, mismatch -> 400 `Chunks on server do not sum up to X but to Y bytes`.
- Put `X-OC-Mtime` (integer) on the final MOVE. Assembling multi-GB files takes time: make sure the proxy read
  timeout and PHP `max_execution_time` allow it, and do not give curl a short timeout.
- GET on a chunk -> 405; `PROPFIND /uploads/<user>/` -> 405; PROPFIND on an upload folder in progress (to list
  chunks) is UNVERIFIED. Abandoned upload folders are removed by the daily `UploadCleanup` job after
  `cache_chunk_gc_ttl` of inactivity (default 86400 s = 24 h). The legacy `OC-Chunked: 1` header is obsolete.

---

## 7. SEARCH

```bash
scripts/ncloud search --name "%.pdf" --path /Travel --after 2026-01-01T00:00:00Z --limit 20 -l
scripts/ncloud search --mime image/ --min-size 5000000 --json
scripts/ncloud search --name invoice --mime application/pdf --files-only --limit 10
```

Flag mapping: `--name X` -> `d:like d:displayname` (wrapped as `%X%` when it has no `%`); `--mime a/` ->
`d:like getcontenttype a/%`, `--mime a/b` -> `d:eq`; `--min-size` / `--max-size` -> `d:gt` / `d:lt oc:size`;
`--after` -> `d:gt d:getlastmodified`; several conditions -> `d:and`; `--path` becomes the scope `/files/<user><path>`;
order `d:getlastmodified` descending (`--asc` reverses); `--limit` -> `d:nresults` (CLI default 50); `--files-only`
-> `<d:not><d:is-collection/></d:not>` (`d:resourcetype` can be selected but not searched, so `d:eq` on it fails).

```bash
scripts/ncloud call SEARCH /remote.php/dav/ -H 'Content-Type: text/xml' --body-file search.xml
curl -sS -u "$AUTH" -X SEARCH -H 'Content-Type: text/xml' "$NC/remote.php/dav/" --data-binary @search.xml
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<d:searchrequest xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns"
                 xmlns:ns="https://github.com/icewind1991/SearchDAV/ns">
  <d:basicsearch>
    <d:select><d:prop>
      <d:displayname/><d:getcontenttype/><d:getcontentlength/><d:getlastmodified/><d:resourcetype/>
      <oc:fileid/><oc:size/><oc:permissions/><d:getetag/><nc:has-preview/>
    </d:prop></d:select>
    <d:from><d:scope><d:href>/files/alice/Travel docs</d:href><d:depth>infinity</d:depth></d:scope></d:from>
    <d:where><d:and>
      <d:like><d:prop><d:displayname/></d:prop><d:literal>%.md</d:literal></d:like>
      <d:gt><d:prop><oc:size/></d:prop><d:literal>0</d:literal></d:gt>
      <d:gt><d:prop><d:getlastmodified/></d:prop><d:literal>2025-01-01T00:00:00Z</d:literal></d:gt>
      <d:not><d:is-collection/></d:not>
    </d:and></d:where>
    <d:orderby><d:order><d:prop><d:getlastmodified/></d:prop><d:descending/></d:order></d:orderby>
    <d:limit><d:nresults>50</d:nresults><ns:firstresult>0</ns:firstresult></d:limit>
  </d:basicsearch>
</d:searchrequest>
```

The response is the same `d:multistatus` (reuse the §1.4 parser), with hrefs like
`/remote.php/dav/files/alice/Travel%20docs/r%c3%a9sum%c3%a9.md`; no hits = an empty `<d:multistatus/>`.

- Send SEARCH only to `/remote.php/dav/` (other URLs -> 501). The scope `d:href` must start with `/files/<user>`,
  may continue into a subfolder, and is **raw UTF-8, not percent-encoded**.
- **`d:depth` is ignored: SEARCH always recurses through the whole scope subtree** (`FileSearchBackend::isValidScope`
  does not read it; depth 0 still matched a file five levels down). To limit depth, narrow the scope or filter by
  href depth on the client.
- Searchable and sortable: `d:displayname`, `d:getcontenttype`, `d:getlastmodified`, `d:creationdate`,
  `nc:upload_time`, `oc:size`, `oc:favorite`. Searchable, not sortable: `oc:fileid`, `oc:owner-id` (only equal to
  yourself). Sortable only: `nc:last_activity`. **Select only**: `d:resourcetype`, `d:getcontentlength`,
  `d:getetag`, `oc:permissions`, `oc:checksums`, `oc:id`, `nc:has-preview`, `oc:owner-display-name` — using them in
  `d:where` -> 400.
- Operators: `d:eq`, `d:gt`, `d:gte`, `d:lt`, `d:lte`, `d:like` (SQL `%` / `_`, **case-insensitive**), `d:and`,
  `d:or`, `d:not`, `d:is-collection`. At most **100 operators** per query (more -> 500
  `maximum operator limit of 100 exceeded`). Date literals: ISO 8601 (`2025-01-01T00:00:00Z`) or unix seconds.
- Without `d:limit` the cap is 100. Offset via `<ns:firstresult>` (namespace
  `https://github.com/icewind1991/SearchDAV/ns`), or use the §2.4 `X-NC-Paginate` headers (large `nresults`, then
  page with headers).
- Results contain only nodes the user can read, including team folders and external mounts, but only as far as
  the file cache knows (changes made directly on external storage need `occ files:scan`, §13).

Common conditions:

```xml
<d:like><d:prop><d:displayname/></d:prop><d:literal>%.pdf</d:literal></d:like>                      <!-- extension -->
<d:like><d:prop><d:getcontenttype/></d:prop><d:literal>image/%</d:literal></d:like>                  <!-- MIME family -->
<d:gte><d:prop><oc:size/></d:prop><d:literal>104857600</d:literal></d:gte>                           <!-- >= 100 MiB -->
<d:gt><d:prop><nc:upload_time/></d:prop><d:literal>1767225600</d:literal></d:gt>                     <!-- upload time -->
<d:eq><d:prop><oc:fileid/></d:prop><d:literal>12345</d:literal></d:eq>                               <!-- path of a fileid -->
```

There is no dedicated "recent files" REPORT; the Files app sends a SEARCH:
`and( or( not(getcontenttype eq httpd/unix-directory), oc:size eq 0 ), or( getlastmodified gt <now-14d>, nc:upload_time gt <now-14d> ) )`,
`orderby nc:last_activity descending`, `nresults 100` (constants from upstream `apps/files/src/services/Recent.ts`).

---

## 8. REPORT (favorites / system tags) and PROPPATCH

```bash
scripts/ncloud favorite list                   # REPORT oc:filter-files (oc:favorite 1) on the user's files root
scripts/ncloud favorite on /Documents/a.pdf    # PROPPATCH <oc:favorite>1</oc:favorite>; off -> 0
scripts/ncloud call REPORT /remote.php/dav/files/alice/ -H 'Content-Type: application/xml' --body-file report.xml
```

```bash
curl -sS -u "$AUTH" -X REPORT -H 'Content-Type: application/xml; charset=utf-8' "$NC/remote.php/dav/files/$U/" --data-binary @- <<'XML'
<oc:filter-files xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns">
  <oc:filter-rules>
    <oc:favorite>1</oc:favorite>            <!-- or <oc:systemtag><tagid></oc:systemtag> (repeat = AND), <oc:circle>…</oc:circle> -->
  </oc:filter-rules>
  <d:prop><oc:fileid/><d:getlastmodified/><oc:favorite/><d:resourcetype/><oc:size/></d:prop>
  <d:limit><d:nresults>100</d:nresults><nc:firstresult>0</nc:firstresult></d:limit>
</oc:filter-files>
XML
```

- Send it to a **folder** URL in the file tree; it recurses from there (`/files/<user>/` for everything). Returns 207
  (no hits = empty multistatus).
- Missing `oc:filter-rules` -> 400 `Missing filter-rule block in request`; unknown tag id -> 412
  `Cannot filter by non-existing tag`.
- The offset element is **`<nc:firstresult>`** (Nextcloud namespace), unlike SEARCH's `ns:firstresult`.
  Favorites/circles are fetched in full and then sliced, so a limit does not save server work. `X-NC-Paginate`
  headers work here too.
- PROPPATCH for favorites (the body the CLI sends):
  `<d:propertyupdate xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns"><d:set><d:prop><oc:favorite>1</oc:favorite></d:prop></d:set></d:propertyupdate>`
  -> 207 with a status per property. `FilesPlugin` also has PROPPATCH handlers for `d:lastmodified` and
  `d:creationdate` (UNVERIFIED).

---

## 9. Trash bin

```bash
scripts/ncloud trash list --json                     # PROPFIND Depth 1 /trashbin/<user>/trash/
scripts/ncloud trash restore "old.d1767225600"       # MOVE trash/<name> -> restore/<name>
scripts/ncloud trash delete "old.d1767225600" --yes  # DELETE trash/<name> (permanent)
scripts/ncloud trash empty --yes                     # DELETE trash/ (permanent)
```

```bash
curl -sS -u "$AUTH" -X PROPFIND -H 'Depth: 1' "$NC/remote.php/dav/trashbin/$U/trash/" --data-binary @- <<'XML'
<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns"><d:prop>
 <d:resourcetype/><d:getcontentlength/><d:getlastmodified/><oc:fileid/><oc:size/>
 <nc:trashbin-filename/><nc:trashbin-original-location/><nc:trashbin-deletion-time/><nc:trashbin-title/>
 <nc:trashbin-deleted-by-id/><nc:trashbin-deleted-by-display-name/><nc:trashbin-backend/>
</d:prop></d:propfind>
XML
curl -sS -u "$AUTH" -o x.pdf "$NC/remote.php/dav/trashbin/$U/trash/report.pdf.d1767225600"        # download
curl -sS -u "$AUTH" -X MOVE -H "Destination: $NC/remote.php/dav/trashbin/$U/restore/x" \
  "$NC/remote.php/dav/trashbin/$U/trash/report.pdf.d1767225600"                                     # restore (target name ignored)
curl -sS -u "$AUTH" -X DELETE "$NC/remote.php/dav/trashbin/$U/trash/report.pdf.d1767225600"        # delete permanently
curl -sS -u "$AUTH" -X DELETE "$NC/remote.php/dav/trashbin/$U/trash/"                              # empty the trash bin
```

```xml
<d:response><d:href>/remote.php/dav/trashbin/alice/trash/report.pdf.d1767225600</d:href>
 <d:propstat><d:prop><d:resourcetype/><d:getcontentlength>234536</d:getcontentlength>
  <nc:trashbin-filename>report.pdf</nc:trashbin-filename>
  <nc:trashbin-original-location>Inbox/report.pdf</nc:trashbin-original-location>
  <nc:trashbin-deletion-time>1767225600</nc:trashbin-deletion-time><nc:trashbin-deleted-by-id>alice</nc:trashbin-deleted-by-id>
  <nc:trashbin-backend>OCA\Files_Trashbin\Trash\LegacyTrashBackend</nc:trashbin-backend><oc:fileid>12345</oc:fileid>
 </d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>
```

- Node names are `<original name>.d<deletion unix time>`; folders have `d:collection` and a trailing slash and can be
  PROPFINDed further. `trashbin-original-location` is relative to the files root, without a leading `/`. The first
  entry is the collection itself (the CLI drops it).
- Restore = MOVE to `/restore/<any name>` (`RestoreFolder::moveInto` only calls `restore()`): the item returns to its
  original location, renamed on a name clash; if the original parent is gone or not writable it lands in the files
  root. Free space minus size < 64 KiB -> 507.
- Permanent delete / empty -> 403 `Not allowed to delete items from the trash bin` when the system config
  `files.trash.delete` is `false`. Whether team-folder trash (its own backend) shows up in the same listing is
  UNVERIFIED.

---

## 10. Versions

```bash
scripts/ncloud versions list /Documents/a.pdf --json            # fileid -> PROPFIND Depth 1 /versions/<user>/versions/<fileid>/
scripts/ncloud versions get /Documents/a.pdf 1767225600 > old.pdf
scripts/ncloud versions restore /Documents/a.pdf 1767225600     # MOVE versions/<fileid>/<ts> -> restore/target
```

```bash
FID=$(scripts/ncloud fileid /Documents/a.pdf)
curl -sS -u "$AUTH" -X PROPFIND -H 'Depth: 1' "$NC/remote.php/dav/versions/$U/versions/$FID/" --data-binary @- <<'XML'
<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:nc="http://nextcloud.org/ns"><d:prop>
 <d:getcontentlength/><d:getlastmodified/><d:getcontenttype/><d:getetag/><nc:version-label/><nc:version-author/><nc:has-preview/>
</d:prop></d:propfind>
XML
curl -sS -u "$AUTH" -o old.pdf "$NC/remote.php/dav/versions/$U/versions/$FID/1767225600"                    # download a version
curl -sS -u "$AUTH" -X MOVE -H "Destination: $NC/remote.php/dav/versions/$U/restore/target" \
  "$NC/remote.php/dav/versions/$U/versions/$FID/1767225600"                                                  # restore (target name ignored)
```

- Version nodes are named by unix time (`…/versions/<fileid>/<timestamp>`), with `d:getcontentlength`,
  `d:getlastmodified`, `d:getcontenttype`, `d:getetag` (= the timestamp) and `nc:has-preview`;
  `nc:version-label` / `nc:version-author` are 404 when unset. The collection itself has every property 404 (normal).
- Restoring first saves the current content as a new version. Delete a version with `DELETE <version href>`. Label
  one with PROPPATCH on the version node:
  `<d:propertyupdate xmlns:d="DAV:" xmlns:nc="http://nextcloud.org/ns"><d:set><d:prop><nc:version-label>final draft</nc:version-label></d:prop></d:set></d:propertyupdate>`.
  Unknown or unreadable fileid -> 404. Retention follows `versions_retention_obligation` (default `auto`). Version
  behaviour on external storage is UNVERIFIED.

---

## 11. Comments and tags (brief)

Not wrapped by the CLI; use `call` or curl.

```bash
# comments: list (REPORT), add (POST JSON; UNVERIFIED), edit (PROPPATCH oc:message), delete (DELETE the node)
curl -sS -u "$AUTH" -X REPORT "$NC/remote.php/dav/comments/files/$FID/" --data-binary \
  '<oc:filter-comments xmlns:oc="http://owncloud.org/ns"><oc:limit>20</oc:limit><oc:offset>0</oc:offset></oc:filter-comments>'
curl -sS -u "$AUTH" -X POST -H 'Content-Type: application/json' "$NC/remote.php/dav/comments/files/$FID/" \
  -d '{"actorType":"users","verb":"comment","message":"text"}'            # 201 + Content-Location
# system tags: catalogue, tags of one file, assign / unassign
TAGPROPS='<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns"><d:prop><oc:id/><oc:display-name/><oc:user-visible/><oc:user-assignable/><oc:can-assign/><nc:color/></d:prop></d:propfind>'
curl -sS -u "$AUTH" -X PROPFIND -H 'Depth: 1' "$NC/remote.php/dav/systemtags/" --data-binary "$TAGPROPS"                        # catalogue
curl -sS -u "$AUTH" -X PROPFIND -H 'Depth: 1' "$NC/remote.php/dav/systemtags-relations/files/$FID/" --data-binary "$TAGPROPS"   # tags of a file
curl -sS -u "$AUTH" -X PUT "$NC/remote.php/dav/systemtags-relations/files/$FID/<tagid>"   # assign -> 201; 412 unknown tag; 403 not assignable; DELETE same URL = unassign
```

- Comment properties for PROPFIND: `oc:id oc:parentId oc:verb oc:actorId oc:actorDisplayName oc:creationDateTime
  oc:message oc:isUnread oc:mentions …`; the `oc:comments-href` file property gives the base URL. Mark as read:
  PROPPATCH `<oc:readMarker>` on the collection.
- Create a tag: `POST /remote.php/dav/systemtags` with JSON `{"name":"Project A","userVisible":true,"userAssignable":true}`
  -> 201 + `Content-Location` (UNVERIFIED). Find files by tag with §8's `oc:systemtag`; add `<nc:system-tags/>` to a
  normal PROPFIND to see a file's tags.

---

## 12. fileid <-> path

```bash
scripts/ncloud fileid /notes.md        # PROPFIND Depth 0 <oc:fileid/> -> 12345
scripts/ncloud path 12345              # SEARCH oc:fileid eq -> /notes.md (exit 4 when not found)
```

- path -> fileid: PROPFIND Depth 0 for `oc:fileid` (§2).
- fileid -> path (recommended): SEARCH `d:eq oc:fileid` (§7 example, `nresults 1`), unquote `d:href` and strip
  `/remote.php/dav/files/<user>`. Empty multistatus = missing or not readable by this user.
- fileid -> parent folder (web redirect): `HEAD $NC/f/<fileid>` (Basic auth) -> 303 with
  `location: /apps/files/files/<fileid>?dir=/Travel%20docs&openfile=true`; `dir=` is the **parent folder**
  (percent-encoded) and the file name is not in the URL. An unknown id still gets a 303 (without `dir=`), so it is no
  existence check. Human-facing link: `$NEXTCLOUD_URL/f/<fileid>`.
- `oc:id` / `OC-FileId` = `str(fileid).zfill(8) + instanceid` (instance id from `occ config:system:get instanceid`,
  starts with `oc`). Ask for `oc:fileid` rather than parsing it.
- Short-lived public download (OCS, not DAV; creates a token; UNVERIFIED):
  `POST /ocs/v2.php/apps/dav/api/v1/direct?format=json` with `OCS-APIRequest: true`, `fileId=<fileid>`,
  `expirationTime=3600` (1…86400, default 28800) -> `data.url = $NC/remote.php/direct/<token>`, anonymous GET until
  it expires. Files only (400), must be readable (403), unknown id 404. For long-lived public URLs use a link share
  plus raw serving (filehost skill).

---

## 13. Team folders, external storage, public share DAV

Everything is mounted under the same `/remote.php/dav/files/<user>/` tree; tell mounts apart by properties:

| Mount (example) | `nc:mount-type` | `nc:is-mount-root` | Other |
|---|---|---|---|
| `/Team/` (team folder, formerly group folder) | `group` | `true` | `nc:group-folder-id <id>`, `nc:acl-enabled` (empty = ACL off), `nc:acl-can-manage`; own perms e.g. `RMGDNVCK` |
| `/External/` (external storage) | `external` | `true` | own perms e.g. `RMGNVCK`; `oc:share-types` contains `3` when it has a link share |
| external storage with sharing disabled | `external` | `true` | own perms without `R` (e.g. `MGNVCK`): cannot be shared |
| shared with me | `shared` | share root: `true` (UNVERIFIED) | perms include `S` |
| everything else | empty | `false` | |

- External storage only shows what the file cache knows: changes made directly on the backend are invisible to
  PROPFIND and SEARCH until rescanned, e.g.
  `scripts/ncloud occ --yes -- files:scan --path=/alice/files/External/<subtree>` (a write; only after the user
  agrees; the external storage "check for changes" setting is UNVERIFIED). **Never run a broad `files:scan` while an
  external storage's backing mount is missing** — the scanner treats an empty mount as deleted and wipes its file
  cache rows. Scan explicit subtrees, and record such hazards (folders never to scan) in the site notes
  (`SITE_NOTES.md`). See `OCC.md` for `files:scan`.
- Mount quota properties are `-3` (unlimited); a mount's `oc:size` counts toward its parent's `oc:size`.
- DELETE on external storage copies the bytes into the home trash bin (§5, UNVERIFIED); team folders have their own
  trash backend; versions on external storage are UNVERIFIED. MOVE across mounts is copy + delete (§5).

### 13.1 Public share DAV (anonymous, `/public.php/dav/files/<token>/`)

The CLI does not wrap it; use curl.

```bash
curl -sS -X PROPFIND -H 'Depth: 1' "$NC/public.php/dav/files/<token>/"                                   # no password
curl -sS -u 'anonymous:<share-password>' -X PROPFIND -H 'Depth: 1' "$NC/public.php/dav/files/<token>/"   # password-protected share
curl -sS -T ./a.pdf -H 'X-NC-Nickname: agent' "$NC/public.php/dav/files/<token>/a.pdf"                    # file request upload
```

- No app password: call `/public.php/dav/files/<token>/<path>` directly; the PROPFIND/PUT/MKCOL/MOVE forms of this
  file apply, limited by the share's permissions (writes to a read-only share are rejected).
- **Password-protected shares** use Basic auth with user `anonymous` and the **share password** (docs). Observed on
  Nextcloud 33: 207 with the share password, 401 without. Missing or wrong share passwords are failed logins that
  land in the same per-IP brute-force bucket as everything else (§14) — do not retry.
- **Send no cookies to password-protected shares** (no curl `-b`/`-c` cookie jar): a request that carries cookies
  but fails the strict-cookie check gets `412 Strict cookie check failed` (source `PublicAuth.php`).
- **File drop** (`share create … --perm upload`, permission 4, no READ): only PUT, MKCOL and the chunked-upload
  MOVE are allowed, every other method -> 405; MKCOL always pretends 201; on a name clash the file name may be
  made unique (source `FilesDropPlugin.php`).
- **File request** (a file drop whose share `attributes` contain `fileRequest/enabled=true`; this is what the web
  UI's "file request" creates): PUT and MKCOL must carry `X-NC-Nickname: <name>` (after URL-decoding: not blank, not
  starting with `.`, a valid path segment), else `400 A nickname header is required for file requests`; uploads land
  in a `/<nickname>/` subfolder. A plain file drop accepts the header too (and then also uses the subfolder)
  (source `apps/dav/lib/Files/Sharing/FilesDropPlugin.php`).
- The strict-cookie and nickname behaviours are source-derived, not verified live.

---

## 14. Error codes and brute-force protection

Error bodies are XML; the CLI's `_dav_error_message()` extracts `<s:message>` and prints it after `HTTP <code>`:

```xml
<d:error xmlns:d="DAV:" xmlns:s="http://sabredav.org/ns">
  <s:exception>Sabre\DAV\Exception\NotFound</s:exception>
  <s:message>File with name /does-not-exist.txt could not be located</s:message>
</d:error>
```

WebDAV specifics (full table and fixes in `TROUBLESHOOTING.md`):

- `200` can be the HTML page returned by GET on a folder (§4). `207` needs a check of every propstat / property status.
- `400`: PUT body != `Content-Length`, chunk sum mismatch, missing `Destination`, SEARCH on a non-searchable property
  (e.g. `d:eq` on `d:resourcetype`), REPORT without `oc:filter-rules`, forbidden file name, file request without
  `X-NC-Nickname` (§13.1).
- `401`: wrong or revoked credentials, a 2FA account using its login password, password login disabled -> use an
  app password. **Every 401 counts toward brute-force protection; never retry.**
- `405`: MKCOL on an existing folder, PROPFIND `/uploads/<user>/`, GET on a chunk, disallowed method on a file drop.
  `409`: missing parent, PUT to a folder. `412`: `Overwrite: F` clash, `If-Match` mismatch, unknown tag, strict cookie
  check. `413`: only a proxy or storage backend limit. `423`: file lock, back off exponentially 1–30 s. `500`: SEARCH
  with more than 100 operators. `501`: SEARCH sent to the wrong URL. `507`: quota, or not enough room to restore
  from the trash bin.
- **Brute-force protection** (Nextcloud core, `auth.bruteforce.protection.enabled`, on by default): each failed
  login from a source IP adds a delay of 0.1 s x 2^n (n = failures from that IP in the last 12 h), capped at 25 s
  (reached after about 8 failures); with more than 10 failures in 12 h **and** more than 10 in the last 30 min the
  server answers 429. The source IP is what Nextcloud sees after reverse-proxy handling (`trusted_proxies`,
  `forwarded_for_headers`): agents behind the same reverse proxy or on the same docker host may all appear as one
  address and share one bucket, so one agent's bad password (or bad share password, or a stale MCP secret) slows
  down or locks out every agent. Allow-listed ranges only help if the address Nextcloud sees is in them.
- Before running loops check `scripts/ncloud caps --section bruteforce` (`delay`, `allow-listed` for the caller).
  Stop at the first 401. Inspect with `scripts/ncloud occ -- security:bruteforce:attempts <ip>`; reset (a write,
  only with the user's consent) with `scripts/ncloud occ --yes -- security:bruteforce:reset <ip>`.
  `ratelimit.protection` does not apply to `/remote.php/dav/*`, but big PROPFIND/SEARCH requests are expensive.

---

## 15. Decision rules

- **Bytes or the file tree** -> WebDAV (this file): list, stat, get, put, mkdir, mv, cp, rm, search, trash,
  versions, favorites, tags, comments, fileid. Works from any runtime that has `curl` + `python3`.
- **Share metadata** (create, list, update, delete shares; tokens; permissions; expiry) -> OCS (`API_OCS.md`);
  WebDAV only tells you that something is shared (`oc:share-types`, `nc:sharees`).
- **Admin state** (`files:scan`, config, apps, brute-force reset, `files.trash.delete`, trash size) -> occ
  (`OCC.md`); never call occ inside a per-file loop.
- **Cross-app semantic work** -> MCP (`MCP.md`, loaded on demand); bulk file I/O still goes through WebDAV.
- Defaults: list with `ls` (Depth 1, explicit properties, `Prefer: return=minimal`; `X-NC-Paginate` above ~500
  entries); find with `search` (narrow scope, depth is ignored, <= 100 operators, page with `nresults` +
  `firstresult`); upload below 64 MiB as one PUT and above it chunked (automatic in the CLI); many small files can
  use bulk upload `POST /remote.php/dav/bulk` (multipart/related, each part needs `X-File-Path`, `Content-Length`,
  and `X-File-Md5` or `OC-Checksum`; not covered here, UNVERIFIED); always percent-encode URLs but never the SEARCH
  scope; no cookie jar for password-protected public shares (412); `X-NC-Nickname` for file request uploads
  (§13.1); try a small file before deleting large files on external storage.
