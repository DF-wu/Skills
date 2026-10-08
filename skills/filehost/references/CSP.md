# CSP.md - Content-Security-Policy of raw links

Every raw response carries a `Content-Security-Policy`. Without configuration it is a fallback that **does not
even run JavaScript**, so "blank page / buttons do nothing / external images missing" is almost always the CSP.

In this file `ncloud` means the nextcloud-use CLI: `../nextcloud-use/scripts/ncloud` when the working directory
is the filehost skill root. `https://cloud.example.com` and `<token>` are placeholders.

## Contents

1. Priority chain
2. What the hard fallback blocks
3. filehost / ncloud presets
4. Custom CSP: common needs
5. Two ways to set it: per-share (API) vs system `raw_csp` (occ)
6. Debugging

---

## 1. Priority chain (`CspManager::determineCspForRequest`)

First match wins:

1. System config `raw_csp.token.<token>` (exact token)
2. **Per-share CSP** (DB, the `csp` of `POST raw-share/{id}`; only while that share is enabled)
3. `raw_csp.path_prefix`: absolute (starting with `/apps/files_sharing_raw`; `/raw/...` is normalized to that
   form first) or relative (the path after the token, e.g. `/html/`); longest match wins
4. `raw_csp.path_contains`: substring; a value starting with `/` is matched as a literal segment (e.g. `/html/`)
5. `raw_csp.extension.<ext>` (lowercase extension)
6. `raw_csp.mimetype.<mime>`
7. **Hard fallback**

A system `raw_csp` rule value can be a string, an array of directive strings, or a `{directive: sources}`
object. **Directive filtering applies only to the associative `{directive: sources}` form**: it keeps only
`base-uri child-src connect-src default-src font-src form-action frame-ancestors frame-src img-src manifest-src
media-src object-src sandbox script-src style-src upgrade-insecure-requests worker-src` and drops anything else.
Strings, string arrays and the **per-share CSP (set via the API)** only go through `sanitizeCspString()`, which
replaces control characters with spaces and collapses whitespace - **directives are not filtered**. A misspelled
directive is neither rejected nor reported; the browser just ignores it, so check the response header after
setting a policy (section 6).

## 2. What the hard fallback blocks

```
sandbox; default-src 'none'; style-src data: 'unsafe-inline'; img-src data:; media-src data:; font-src data:; frame-src data:
```

- `sandbox` without `allow-scripts` -> **no script runs** (inline or external); also no `allow-same-origin`,
  no `allow-forms`.
- `default-src 'none'` + `data:` only -> linked CSS, image and font files and `fetch()` are all blocked; only
  **inline `<style>` / `style=""`** and **`data:` URI** images and fonts work.
- Good for: plain HTML, static pages converted from Markdown, untrusted content.

## 3. Presets (`ncloud raw presets` / `scripts/filehost presets`)

Source of truth: `CSP_PRESETS` in `../nextcloud-use/scripts/ncloud`.

| Preset | Value | Allows | Blocks |
|---|---|---|---|
| `locked` | empty string -> clears the per-share CSP, back to the fallback | inline CSS, `data:` images | JS, linked assets |
| `site` (default for folders / HTML-like files) | `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'none'; object-src 'none'` | same-origin JS/CSS/images/fonts/media, inline script/style, same-origin fetch | any external origin, being iframed, form submission |
| `cdn` | `site` + `script-src ... 'unsafe-eval' https:`, `style-src ... https:`, `img-src ... https:`, `font-src ... https:`, `media-src ... https:`, `connect-src 'self' https:`, `frame-src https:` | libraries, fonts, APIs and iframes from any https origin | being iframed |
| `embed` | identical to `cdn` (also with `'unsafe-eval'`) except `frame-ancestors 'none'` becomes `frame-ancestors *` | everything `cdn` allows, plus being iframed by any site | - |
| `asset` | `default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'; sandbox` | direct image/media serving | JS |

`'self'` is the Nextcloud origin (e.g. `https://cloud.example.com`): `assets/app.js` inside the same raw site is
self, and so is any other token's raw URL on the same host.

Automatic choice in `filehost publish`: folders and `.html/.htm/.xhtml/.svg` files -> `site`; other single files
(png, json, pdf ...) -> none (fallback). `asset` is never automatic (`--preset asset`). SVG counts as HTML-like:
the CSP applies when the SVG URL is opened directly (an SVG referenced via `<img>` never runs scripts anyway).

## 4. Custom CSP: common needs

| Need | Add |
|---|---|
| Tailwind / Alpine / Chart.js from a CDN | `script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com` (or the `cdn` preset) |
| Google Fonts | `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com` |
| Page `fetch()`es an external API | `connect-src 'self' https://api.example.com` |
| Embedded YouTube | `frame-src https://www.youtube.com https://www.youtube-nocookie.com` |
| Page embedded by other sites (wikis, chat apps, dashboards) | `frame-ancestors *` (or a list of origins). The CSP must contain `frame-ancestors`: core also sends `X-Frame-Options: SAMEORIGIN`, and browsers prefer CSP `frame-ancestors` when present. The fallback and `asset` lack it, so cross-site iframes are blocked by XFO (`<img>` embedding is unaffected) |
| WebAssembly | `script-src ... 'wasm-unsafe-eval'` |
| Web Worker | `worker-src 'self' blob:` |
| Keep `<base>` injection safe | keep `base-uri 'self'` |

Apply with `scripts/filehost csp <name> --csp "..."` or `ncloud raw enable <share_id> --csp "..."`.

## 5. Two ways to set it

**Per-share (recommended)**: travels with the share and disappears when the share is deleted; the caller must be
in `csp_editor_group` (default `admin`). `filehost publish` applies the automatic choice (section 3) when it
creates a share; later re-publishes without `--preset/--csp` **keep** the existing value. `raw disable` ->
enable keeps the CSP too (observed on Nextcloud 33; while disabled `raw get` shows `csp: null`, but the DB
still has it).

**System `raw_csp` (occ, instance-wide)**: for "every `.html` gets this policy" or "this token always gets this
policy".

```bash
# all .html files
ncloud occ --yes -- config:system:set raw_csp extension html --value="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:"
# one token
ncloud occ --yes -- config:system:set raw_csp token <token> --value="default-src 'self'"
# relative path prefix (after the token)
ncloud occ --yes -- config:system:set raw_csp path_prefix /public/ --value="default-src 'self'"
ncloud occ -- config:system:get raw_csp
ncloud occ --yes -- config:system:delete raw_csp
```

Mind the order: `raw_csp.token` beats per-share; `path_prefix/path_contains/extension/mimetype` lose to
per-share. System-level changes need the user's consent.

## 6. Debugging

```bash
curl -sI https://cloud.example.com/raw/<token>/index.html | grep -i '^content-security-policy'
scripts/filehost verify <name>          # prints the csp header
ncloud raw get <share_id>               # the stored per-share csp (null = unset, or raw currently disabled)
```

The browser console lists `Refused to load ... because it violates the following Content Security Policy
directive` with the blocked directive; add what section 4 suggests. CSP changes apply immediately, but the
browser may have cached the old HTML response (up to 5 minutes): add `?v=` or force a reload.
