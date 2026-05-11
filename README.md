# linkmap.py — Website link mapper with broken-link detection

A small Python tool that crawls a website, maps which pages link to which,
and finds broken links along the way. Designed for site audits, content
migrations, and ongoing link-rot monitoring on sites you own.

📋 **Looking to deploy this as a scheduled GitHub Actions workflow with
notifications?** See [DEPLOYMENT.md](DEPLOYMENT.md) for the complete setup,
including optional Drupal author lookup.

## What you get

After running, three files are written:

- **`<output>.json`** — Full link graph in machine-readable form. Every
  crawled page (URL, title, HTTP status), every edge (source → target with
  anchor text), every broken target with its referrers, and stats.
- **`<output>.html`** — Self-contained interactive force-directed graph
  (vis-network from CDN). Open in a browser to explore. Broken targets
  appear in red.
- **`<output>-broken.md`** — Markdown report listing every broken link,
  grouped by target, with each referring page and its anchor text. Drop it
  in Confluence/Notion/Docs and hand it to a content editor.

A companion script **`regen_html.py`** is included for refreshing the HTML
viewer from an existing JSON (e.g., after updating the viewer code) without
re-crawling. Saves a lot of time on large sites.

## Install

Requires Python 3.7+ and two pip packages:

```bash
pip install requests beautifulsoup4
```

On Windows, use `py -m pip install requests beautifulsoup4` if `pip`
isn't on PATH.

## Basic usage

```bash
python linkmap.py https://example.com
```

Defaults: 100 page limit, 0.5 s delay between page fetches, HEAD-checks
all external link targets afterwards, 0.1 s between external checks.
Three output files are written with prefix `linkmap`.

## For Drupal sites

A sensible starting point for a Drupal 9/10/11 site (here scoped to the
Finnish-language section of a multilingual site):

```bash
python linkmap.py https://www.example.com/fi --max-pages 1000 \
  --skip-pattern "^https?://(www\.)?example\.com/(sv|en)(/|$)" \
  --skip-pattern "/user/" \
  --skip-pattern "/admin/" \
  --skip-pattern "/node/\d+/(edit|delete)" \
  --output mysite-fi
```

Each `--skip-pattern` is a Python regex matched anywhere in the URL.
Skipping admin/auth paths avoids false-positive 403s and infinite
query-string spaces (faceted search, filtered views, pagination loops).

On PowerShell use backtick `` ` `` instead of `\` for line continuation.

## All options

```
url                       Starting URL (required)
--max-pages N             Maximum pages to crawl (default 100)
--delay N                 Seconds between internal requests (default 0.5)
--external                Follow external links during crawl (default: no)
--no-check-external       Skip HEAD-checking external link targets
--external-delay N        Seconds between external HEAD checks (default 0.1)
--skip-pattern REGEX      URLs to skip (can be repeated)
--output PREFIX           Output filename prefix (default 'linkmap')
--timeout N               Request timeout in seconds (default 10)
```

## HTML viewer features

Open the generated `<output>.html` in any modern browser. No web server
needed — all data is embedded.

- **Force-directed graph** — pages as nodes, links as arrows. Internal
  pages are blue, external are purple, broken targets are red.
- **Click a node** — see its inbound and outbound links in the right
  sidebar, with anchor text for each link.
- **Filter graph** — type in the filter box to hide non-matching nodes.
  Useful when the graph is too dense to read.
- **Look up URL** — paste a URL into the lookup field to instantly see
  what links to it. Tries exact, case-insensitive, and trailing-slash
  tolerant matching, falls back to substring suggestions if no exact
  match. This is the fastest way to answer "which pages link to /some-page?"
  during content migrations.
- **Search results** — clicking any URL in the inbound/outbound lists
  navigates to that node in the graph and updates the sidebar.

## Regenerating HTML from existing JSON

If you've already crawled a site and just want a fresh HTML viewer (e.g.,
after `linkmap.py` itself has been updated with new viewer features), use:

```bash
python regen_html.py mysite-fi.json
```

This writes a new `mysite-fi.html` using the current `linkmap.py`'s HTML
template, without re-crawling. On a 1000-page site this saves 10–15
minutes compared to a full re-run.

Optionally specify a different output path:

```bash
python regen_html.py mysite-fi.json viewer.html
```

## Example broken-links report

```markdown
# Broken Links Report

- **Site:** https://www.example.com
- **Crawled:** 2026-05-10T16:30:00
- **Pages crawled:** 234
- **External targets checked:** 89
- **Total broken:** 12 (2 internal, 10 external)

## Internal broken pages

### `https://www.example.com/old-event-2019`
- **Reason:** HTTP 404
- **Linked from 3 page(s):**
  - `https://www.example.com/events/archive` — "2019 program"
  - `https://www.example.com/news/2019-recap` — "more details here"
  - `https://www.example.com/sitemap` — "Old event"

## External broken links

### `https://partner-that-no-longer-exists.com/`
- **Reason:** DNS resolution failed
- **Linked from 2 page(s):**
  - `https://www.example.com/partners` — "Partner Site"
  - `https://www.example.com/about` — "our partners"
```

## Broken-link detection — what it catches

- **Internal 4xx/5xx** — pages on your own domain that return error
  codes. These are the most actionable: usually a renamed or deleted
  page that someone still links to internally.
- **External 4xx/5xx** — partner pages, references, downloads that
  have died.
- **DNS-dead external links** — domains that no longer exist
  (`DNS resolution failed`).
- **Connection errors** — refused, reset, no route to host.
- **SSL errors** — expired or invalid certificates.
- **Timeouts** — sites that don't respond in time.

## Domain handling

The crawler treats `example.com` and `www.example.com` as the same site,
so you can start from either URL and follow the redirect without
fragmenting the graph. If your site uses a different subdomain
convention (e.g., `shop.example.com` alongside `example.com` that should
also be treated as same-site), use `--external` to follow those links
during the crawl.

## What it doesn't catch

- **JavaScript-rendered links** — if a page only renders its links via
  client-side JS (some SPAs), the crawler won't see them. Drupal renders
  most content server-side, so this is rarely an issue, but watch out
  for any custom JS modules that lazy-load nav.
- **Anchor fragments** — `/page#section-id` is treated the same as
  `/page`. Whether `#section-id` actually exists on the target isn't
  verified.
- **Image / CSS / JS resources** — only `<a href>` links are followed.
  Broken `<img src>` or `<script src>` won't show up.
- **Auth-required pages** — anything behind login. To scan those,
  add cookies to the `session.headers` block in the script.
- **Some bot-blocked external sites** — Cloudflare and similar may
  return 403 to the crawler even though the page is fine in a browser.
  These appear as "broken" but verify manually before deleting.

## Tips

- For first run on a real site, start small: `--max-pages 50`. Inspect
  the HTML viewer and broken-links report, tune your `--skip-pattern`
  values, then increase the limit.
- The HTML file is portable — data is embedded, no server needed. You
  can email it, drop it in Drive, or check it into version control to
  diff site structure over time.
- For CI / scheduled audits, parse the JSON `broken` array. It's
  easy to alert on `broken_count > 0` in a build pipeline.
- Run weekly or monthly on production sites to catch link rot before
  it accumulates.
- During a content split or migration, use the "Look up URL" feature
  in the HTML viewer to instantly see which pages link to the page
  you're about to change — then plan redirects accordingly.

## Files

- `linkmap.py` — the crawler and HTML generator
- `regen_html.py` — companion script to regenerate HTML from existing JSON
- `drupal_authors.py` — companion script that enriches broken-link data with
  Drupal author info (which content editor's page links to each broken target)
- `<output>.json` — link graph data
- `<output>.html` — interactive viewer
- `<output>-broken.md` — broken-links report
- `<output>-broken-by-author.md` — broken-links grouped by content editor
  (when `drupal_authors.py` has been run)

## Changelog

**1.2** — Added `drupal_authors.py` for Drupal JSON:API author enrichment,
GitHub Actions deployment (see [DEPLOYMENT.md](DEPLOYMENT.md)) with
auto-issue creation, by-author broken-links report, dispatcher index.html
for GitHub Pages.

**1.1** — Broken-link detection (HEAD-checks external targets),
`--skip-pattern` for excluding URLs, www/non-www domain normalization,
"Look up URL" feature in the HTML viewer, `regen_html.py` companion
script, cleaner error categorization (DNS / connection / SSL / timeout).

**1.0** — Initial release. Internal-only link mapping with JSON and
interactive HTML output.

## License

MIT — do whatever you want with it.
