#!/usr/bin/env python3
"""
linkmap.py — Simple website link mapper with broken-link detection.

Crawls a website starting from the given URL, follows internal links
(same-domain only by default), HEAD-checks every external link target
for reachability, and outputs:

  * <output>.json          — full link graph (pages, edges, broken, stats)
  * <output>.html          — interactive force-directed visualization
  * <output>-broken.md     — Markdown report of all broken links

Usage:
    python linkmap.py https://example.com
    python linkmap.py https://example.com --max-pages 200 --delay 0.3
    python linkmap.py https://example.com --skip-pattern '/admin/' --skip-pattern '/user/'
    python linkmap.py https://example.com --no-check-external

Requires:
    pip install requests beautifulsoup4
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Linkmap — {start_url}</title>
<style>
  body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#0e1115; color:#e7e7e7; }}
  #sidebar {{ position:fixed; top:0; right:0; width:380px; height:100vh; padding:20px;
             box-sizing:border-box; background:#181c22; border-left:1px solid #2a2f37;
             overflow-y:auto; }}
  #network {{ width:calc(100% - 380px); height:100vh; }}
  h1 {{ font-size:16px; margin:0 0 12px; color:#7aa2f7; }}
  h2 {{ font-size:12px; margin:18px 0 8px; color:#bb9af7;
        text-transform:uppercase; letter-spacing:.06em; }}
  .stat {{ font-size:12px; color:#9aa5b1; margin:3px 0; }}
  .stat strong {{ color:#fff; font-weight:600; }}
  .stat.bad strong {{ color:#f7768e; }}
  .node-info {{ font-size:12px; line-height:1.5; color:#c5cdd6;
               word-break:break-word; margin-bottom:6px; }}
  .node-info a {{ color:#7aa2f7; }}
  .link-list {{ font-size:11px; max-height:320px; overflow-y:auto;
               border:1px solid #2a2f37; border-radius:4px; padding:6px; }}
  .link-list a {{ color:#7aa2f7; text-decoration:none; display:block;
                 padding:3px 4px; border-radius:3px; }}
  .link-list a:hover {{ background:#2a2f37; color:#a4c1f7; }}
  .link-text {{ color:#666; font-style:italic; margin-left:6px; }}
  .error {{ color:#f7768e; }}
  input {{ font:inherit; padding:6px 8px; border:1px solid #2a2f37;
          background:#0e1115; color:#fff; border-radius:4px; width:100%;
          box-sizing:border-box; }}
  input:focus {{ outline:none; border-color:#7aa2f7; }}
  .legend {{ display:flex; gap:12px; font-size:11px; margin-top:8px; flex-wrap:wrap; }}
  .legend span {{ display:flex; align-items:center; gap:5px; }}
  .legend .dot {{ width:9px; height:9px; border-radius:50%; }}
</style>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
</head>
<body>
<div id="network"></div>
<aside id="sidebar">
  <h1>📊 Linkmap</h1>
  <div class="stat">Start: <strong>{start_url}</strong></div>
  <div class="stat">Domain: <strong>{base_netloc}</strong></div>
  <div class="stat">Crawled: <strong>{pages_crawled}</strong> pages</div>
  <div class="stat">Edges: <strong>{edges_count}</strong> links</div>
  <div class="stat bad">Broken: <strong>{broken_count}</strong> targets</div>
  <div class="legend">
    <span><span class="dot" style="background:#7aa2f7"></span>internal OK</span>
    <span><span class="dot" style="background:#bb9af7"></span>external OK</span>
    <span><span class="dot" style="background:#f7768e"></span>broken</span>
    <span><span class="dot" style="background:#888"></span>not checked</span>
  </div>
  <h2>View</h2>
  <label style="font-size:11px; color:#9aa5b1; display:block; margin-top:6px;">Layout</label>
  <select id="layout-mode" style="width:100%; box-sizing:border-box; padding:6px 8px; background:#0e1115; color:#fff; border:1px solid #2a2f37; border-radius:4px; font:inherit; margin-bottom:8px;">
    <option value="force">Force-directed (default)</option>
    <option value="hierarchy-ud">Hierarchy (top-down)</option>
    <option value="hierarchy-lr">Hierarchy (left-right)</option>
  </select>
  <label style="font-size:11px; color:#9aa5b1; display:block;">Color</label>
  <select id="color-mode" style="width:100%; box-sizing:border-box; padding:6px 8px; background:#0e1115; color:#fff; border:1px solid #2a2f37; border-radius:4px; font:inherit;">
    <option value="status">Status (default)</option>
    <option value="section">URL section</option>
  </select>
  <h2>Filter graph</h2>
  <input id="search" placeholder="Filter nodes by URL or title…">
  <h2>Look up URL</h2>
  <input id="lookup" placeholder="Paste a URL to see what links to it…">
  <div id="lookup-result"></div>
  <h2>Selected node</h2>
  <div id="selected">Click a node to see its inbound &amp; outbound links.</div>
</aside>
<script>
const DATA = {data_json};

const brokenSet = new Set(DATA.broken.map(b => b.target));

const nodes = [];
const seen  = new Set();
function pushNode(url, page) {{
  if (seen.has(url)) return;
  seen.add(url);
  const internal = url.includes(DATA.base_netloc);
  const isBroken = brokenSet.has(url);
  let color;
  if (isBroken)        color = '#f7768e';
  else if (page)       color = internal ? '#7aa2f7' : '#bb9af7';
  else                 color = internal ? '#7aa2f7' : '#888';
  let label = url;
  try {{
    const u = new URL(url);
    label = u.pathname && u.pathname !== '/' ? u.pathname : u.hostname;
  }} catch (_) {{}}
  if (page && page.title) label = page.title;
  if (label.length > 28) label = label.slice(0, 25) + '…';
  nodes.push({{
    id: url,
    label,
    color,
    size: page ? 8 : 5,
    title: (page && page.title ? page.title + '\\n' : '') + url,
  }});
}}

for (const [url, page] of Object.entries(DATA.pages)) pushNode(url, page);
const edges = [];
for (const e of DATA.edges) {{
  pushNode(e.target, DATA.pages[e.target]);
  edges.push({{
    from: e.source, to: e.target, arrows: 'to',
    color: {{ color: brokenSet.has(e.target) ? '#f7768e' : '#3a4150',
              opacity: brokenSet.has(e.target) ? 0.7 : 0.45 }},
    smooth: false,
  }});
}}

const visNodes = new vis.DataSet(nodes);
const visEdges = new vis.DataSet(edges);

const LAYOUT_OPTIONS = {{
  force: {{
    layout: {{ hierarchical: false }},
    physics: {{
      enabled: true,
      stabilization: {{ iterations: 200 }},
      barnesHut: {{ gravitationalConstant: -3500, springLength: 110, avoidOverlap: 0.3 }},
    }},
  }},
  'hierarchy-ud': {{
    layout: {{
      hierarchical: {{
        enabled: true,
        direction: 'UD',
        sortMethod: 'directed',
        nodeSpacing: 90,
        levelSeparation: 130,
        shakeTowards: 'roots',
      }},
    }},
    physics: false,
  }},
  'hierarchy-lr': {{
    layout: {{
      hierarchical: {{
        enabled: true,
        direction: 'LR',
        sortMethod: 'directed',
        nodeSpacing: 70,
        levelSeparation: 200,
        shakeTowards: 'roots',
      }},
    }},
    physics: false,
  }},
}};

const PALETTE = ['#7aa2f7', '#bb9af7', '#9ece6a', '#e0af68', '#7dcfff', '#ff9e64', '#73daca', '#c0caf5', '#41a6b5', '#d19a66'];

function recolorByStatus() {{
  const updated = nodes.map(n => {{
    const internal = n.id.includes(DATA.base_netloc);
    const isBroken = brokenSet.has(n.id);
    const hasData = DATA.pages[n.id];
    let color;
    if (isBroken)       color = '#f7768e';
    else if (hasData)   color = internal ? '#7aa2f7' : '#bb9af7';
    else                color = internal ? '#7aa2f7' : '#888';
    return {{ id: n.id, color }};
  }});
  visNodes.update(updated);
}}

function recolorBySection() {{
  const colorByPrefix = {{}};
  let idx = 0;
  const updated = nodes.map(n => {{
    if (brokenSet.has(n.id)) return {{ id: n.id, color: '#f7768e' }};
    let prefix = '(root)';
    try {{
      const u = new URL(n.id);
      const parts = u.pathname.split('/').filter(p => p);
      // For multilingual sites, group by 2nd-level prefix if first is a lang code
      if (parts.length >= 2 && ['fi','sv','en','de','fr','es'].includes(parts[0])) {{
        prefix = parts[0] + '/' + parts[1];
      }} else if (parts.length >= 1) {{
        prefix = parts[0];
      }}
    }} catch (_) {{}}
    if (!(prefix in colorByPrefix)) {{
      colorByPrefix[prefix] = PALETTE[idx % PALETTE.length];
      idx++;
    }}
    return {{ id: n.id, color: colorByPrefix[prefix] }};
  }});
  visNodes.update(updated);
}}

const network = new vis.Network(
  document.getElementById('network'),
  {{ nodes: visNodes, edges: visEdges }},
  {{
    ...LAYOUT_OPTIONS.force,
    nodes: {{ shape: 'dot', font: {{ color: '#e7e7e7', size: 10, strokeWidth: 0 }} }},
    interaction: {{ hover: true, tooltipDelay: 150 }},
  }}
);

document.getElementById('layout-mode').addEventListener('change', e => {{
  const mode = e.target.value;
  network.setOptions(LAYOUT_OPTIONS[mode] || LAYOUT_OPTIONS.force);
}});

document.getElementById('color-mode').addEventListener('change', e => {{
  if (e.target.value === 'section') recolorBySection();
  else recolorByStatus();
}});

function escape(s) {{
  return String(s).replace(/[&<>"]/g, c => ({{ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' }})[c]);
}}

window.showNode = function(url) {{
  const page = DATA.pages[url];
  const broken = DATA.broken.find(b => b.target === url);
  const inb  = DATA.edges.filter(e => e.target === url);
  const outb = DATA.edges.filter(e => e.source === url);

  let html = '<div class="node-info"><strong>URL:</strong> <a href="' + url +
             '" target="_blank" rel="noopener">' + escape(url) + '</a></div>';
  if (page) {{
    if (page.title)  html += '<div class="node-info"><strong>Title:</strong> ' + escape(page.title) + '</div>';
    if (page.status) html += '<div class="node-info"><strong>Status:</strong> ' + page.status + '</div>';
    if (page.error)  html += '<div class="node-info error"><strong>Error:</strong> ' + escape(page.error) + '</div>';
  }}
  if (broken) {{
    html += '<div class="node-info error"><strong>⚠ BROKEN</strong>: ' +
            (broken.status ? 'HTTP ' + broken.status : escape(broken.error || 'unreachable')) + '</div>';
  }}
  if (!page && !broken) {{
    html += '<div class="node-info"><em>External / not checked</em></div>';
  }}

  html += '<h2>Inbound links (' + inb.length + ')</h2>';
  if (inb.length) {{
    html += '<div class="link-list">' + inb.slice(0, 80).map(e =>
      '<a href="javascript:showNode(' + JSON.stringify(e.source) + ')">' +
      escape(e.source) + (e.text ? '<span class="link-text">' + escape(e.text) + '</span>' : '') +
      '</a>'
    ).join('') + '</div>';
  }}

  html += '<h2>Outbound links (' + outb.length + ')</h2>';
  if (outb.length) {{
    html += '<div class="link-list">' + outb.slice(0, 80).map(e =>
      '<a href="javascript:showNode(' + JSON.stringify(e.target) + ')">' +
      escape(e.target) + (e.text ? '<span class="link-text">' + escape(e.text) + '</span>' : '') +
      '</a>'
    ).join('') + '</div>';
  }}

  document.getElementById('selected').innerHTML = html;
  network.selectNodes([url]);
  network.focus(url, {{ scale: 1.0, animation: true }});
}};

network.on('click', e => {{ if (e.nodes[0]) showNode(e.nodes[0]); }});

document.getElementById('search').addEventListener('input', e => {{
  const q = e.target.value.toLowerCase();
  visNodes.update(nodes.map(n => ({{
    id: n.id,
    hidden: q && !n.id.toLowerCase().includes(q) && !(n.label || '').toLowerCase().includes(q),
  }})));
}});

function lookupUrl(input) {{
  const result = document.getElementById('lookup-result');
  const q = input.trim().split('#')[0];
  if (!q) {{ result.innerHTML = ''; return; }}

  // Try exact, then case-insensitive, then trailing-slash-tolerant
  const stripSlash = s => s.replace(/\\/$/, '');
  let match =
    nodes.find(n => n.id === q) ||
    nodes.find(n => n.id.toLowerCase() === q.toLowerCase()) ||
    nodes.find(n => stripSlash(n.id).toLowerCase() === stripSlash(q).toLowerCase());

  if (match) {{
    showNode(match.id);
    result.innerHTML = '<div style="font-size:11px;color:#9ece6a;margin:4px 0;">✓ Found — see Selected node below</div>';
    return;
  }}

  // Substring fallback — show suggestions
  const qLower = q.toLowerCase();
  const suggestions = nodes
    .filter(n => n.id.toLowerCase().includes(qLower))
    .slice(0, 8);

  if (suggestions.length === 1) {{
    showNode(suggestions[0].id);
    result.innerHTML = '<div style="font-size:11px;color:#9ece6a;margin:4px 0;">✓ Substring match — see Selected node</div>';
  }} else if (suggestions.length > 1) {{
    result.innerHTML =
      '<div style="font-size:11px;color:#e0af68;margin:4px 0;">' + suggestions.length + ' matches — pick one:</div>' +
      '<div class="link-list">' +
      suggestions.map(n =>
        '<a href="javascript:showNode(' + JSON.stringify(n.id) + ')">' + escape(n.id) + '</a>'
      ).join('') + '</div>';
  }} else {{
    result.innerHTML = '<div style="font-size:11px;color:#f7768e;margin:4px 0;">No match in graph. The crawler may not have reached this URL.</div>';
  }}
}}

document.getElementById('lookup').addEventListener('input', e => lookupUrl(e.target.value));
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def normalize_url(url):
    url, _ = urldefrag(url)
    return url


def normalize_netloc(netloc):
    """Strip optional 'www.' prefix so e.g. www.example.com == example.com."""
    return netloc[4:] if netloc.startswith("www.") else netloc


def is_internal(url, base_netloc):
    try:
        return normalize_netloc(urlparse(url).netloc) == normalize_netloc(base_netloc)
    except Exception:
        return False


def is_html_response(response):
    ctype = response.headers.get("Content-Type", "").lower()
    if "html" in ctype:
        return True
    binary_or_data = (
        "image/", "video/", "audio/", "font/",
        "application/pdf", "application/zip",
        "application/json", "application/xml",
        "text/css", "text/javascript", "application/javascript",
    )
    if any(t in ctype for t in binary_or_data):
        return False
    try:
        head = response.text[:512].lstrip().lower()
        return head.startswith(("<!doctype", "<html", "<body", "<head"))
    except Exception:
        return False


def matches_skip(url, patterns):
    return any(p.search(url) for p in patterns)


def extract_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        absolute = urljoin(base_url, href)
        absolute = normalize_url(absolute)
        text = " ".join((a.get_text() or "").split())[:100]
        out.append({"url": absolute, "text": text})
    return out


def extract_meta(soup):
    """Pull useful page metadata: og:updated_time, robots unavailable_after.

    Public metadata that's safe to extract without authentication. Helps
    prioritize broken-link triage (stale pages, expiring content).
    """
    meta = {}
    # og:updated_time — when the page was last modified
    tag = soup.find("meta", attrs={"property": "og:updated_time"})
    if tag and tag.get("content"):
        meta["updated_time"] = tag["content"].strip()

    # meta robots — may include unavailable_after for time-bound content
    tag = soup.find("meta", attrs={"name": "robots"})
    if tag and tag.get("content"):
        content = tag["content"].strip()
        meta["robots"] = content
        # Extract unavailable_after timestamp. Format example:
        # "index, follow, unavailable_after: Friday, 12-Jun-26 00:00:00 EEST"
        # The value itself may contain commas, so split on "unavailable_after:" only.
        low = content.lower()
        idx = low.find("unavailable_after:")
        if idx != -1:
            after = content[idx + len("unavailable_after:"):].strip()
            if after:
                meta["unavailable_after"] = after

    # og:type — useful to know if it's article, website, event, etc.
    tag = soup.find("meta", attrs={"property": "og:type"})
    if tag and tag.get("content"):
        meta["og_type"] = tag["content"].strip()

    return meta


def head_check(session, url, timeout=8):
    """Return (status, error) for url. Falls back to GET if HEAD is unsupported."""
    try:
        r = session.head(url, timeout=timeout, allow_redirects=True)
        # Some servers return 405/501 for HEAD; verify with GET
        if r.status_code in (405, 501):
            try:
                r = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
                r.close()
            except Exception:
                pass
        return r.status_code, None
    except requests.exceptions.Timeout:
        return None, "timeout"
    except requests.exceptions.SSLError as e:
        msg = str(e).lower()
        if "certificate" in msg:
            return None, "SSL certificate error"
        return None, "SSL error"
    except requests.exceptions.ConnectionError as e:
        msg = str(e).lower()
        if any(s in msg for s in ("name or service not known", "nodename nor servname",
                                    "name resolution", "getaddrinfo failed")):
            return None, "DNS resolution failed"
        if "connection refused" in msg:
            return None, "connection refused"
        if "connection reset" in msg:
            return None, "connection reset"
        if "no route to host" in msg:
            return None, "no route to host"
        return None, "connection failed"
    except requests.exceptions.TooManyRedirects:
        return None, "too many redirects"
    except Exception as e:
        return None, str(e)[:100]


# ---------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------

def crawl(start_url, max_pages=100, delay=0.5, follow_external=False,
          timeout=10, skip_patterns=None, check_external=True,
          external_delay=0.1):
    start_url = normalize_url(start_url)
    base_netloc = urlparse(start_url).netloc
    skip_patterns = skip_patterns or []

    visited = set()
    queued = {start_url}
    queue = [start_url]
    pages = {}
    edges = []

    session = requests.Session()
    session.headers.update({
        "User-Agent": "linkmap.py/1.1 (+ link mapper & broken-link checker)"
    })

    print(f"Crawling: {start_url}", file=sys.stderr)
    print(f"Domain:   {base_netloc}", file=sys.stderr)
    print(f"Limit:    {max_pages} pages, {delay}s delay between requests", file=sys.stderr)
    if skip_patterns:
        print(f"Skip:     {len(skip_patterns)} pattern(s)", file=sys.stderr)
    print(file=sys.stderr)

    # ---- Phase 1: BFS crawl internal pages ----
    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        if matches_skip(url, skip_patterns):
            continue
        visited.add(url)

        print(f"  [{len(visited):>4}/{max_pages}] {url[:90]}", file=sys.stderr)

        try:
            r = session.get(url, timeout=timeout, allow_redirects=True)
            final = normalize_url(r.url)
        except Exception as e:
            pages[url] = {"title": None, "status": None, "error": str(e)[:140], "outbound": []}
            continue

        if not is_html_response(r):
            pages[url] = {
                "title": None,
                "status": r.status_code,
                "type": r.headers.get("Content-Type", "").split(";")[0].strip(),
                "outbound": [],
            }
            continue

        title = None
        try:
            soup = BeautifulSoup(r.text, "html.parser")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()[:200]
        except Exception:
            soup = None

        outbound_links = extract_links(r.text, final)
        page_meta = extract_meta(soup) if soup else {}
        pages[url] = {
            "title": title,
            "status": r.status_code,
            "outbound": [link["url"] for link in outbound_links],
            **page_meta,
        }

        for link in outbound_links:
            target = link["url"]
            edges.append({"source": url, "target": target, "text": link["text"]})
            internal = is_internal(target, base_netloc)
            if (internal or follow_external) and target not in visited and target not in queued:
                if not matches_skip(target, skip_patterns):
                    queue.append(target)
                    queued.add(target)

        if delay > 0:
            time.sleep(delay)

    # ---- Phase 2: HEAD-check external link targets ----
    external_status = {}
    if check_external:
        external_targets = sorted({
            e["target"] for e in edges
            if not is_internal(e["target"], base_netloc)
            and not matches_skip(e["target"], skip_patterns)
            and e["target"].startswith(("http://", "https://"))
        })
        if external_targets:
            print(f"\nChecking {len(external_targets)} external link target(s)…",
                  file=sys.stderr)
            for i, target in enumerate(external_targets, 1):
                status, err = head_check(session, target, timeout=timeout)
                external_status[target] = {"status": status, "error": err}
                marker = "✗" if (status and status >= 400) or err else "·"
                print(f"  {marker} [{i:>4}/{len(external_targets)}] {target[:90]}"
                      + (f"  → {status or err}" if marker == "✗" else ""),
                      file=sys.stderr)
                if external_delay > 0:
                    time.sleep(external_delay)

    # ---- Phase 3: Compile broken-link list ----
    by_target = {}
    for e in edges:
        by_target.setdefault(e["target"], []).append(e)

    broken = []
    for url, p in pages.items():
        is_broken = (p.get("status") and p["status"] >= 400) or p.get("error")
        if is_broken:
            broken.append({
                "target": url,
                "kind": "internal",
                "status": p.get("status"),
                "error": p.get("error"),
                "linked_from": [
                    {
                        "page": e["source"],
                        "anchor": e["text"],
                        "page_updated": pages.get(e["source"], {}).get("updated_time"),
                        "page_og_type": pages.get(e["source"], {}).get("og_type"),
                        "page_unavailable_after": pages.get(e["source"], {}).get("unavailable_after"),
                    }
                    for e in by_target.get(url, [])
                ],
            })
    for url, info in external_status.items():
        is_broken = (info["status"] and info["status"] >= 400) or info["error"]
        if is_broken:
            broken.append({
                "target": url,
                "kind": "external",
                "status": info["status"],
                "error": info["error"],
                "linked_from": [
                    {
                        "page": e["source"],
                        "anchor": e["text"],
                        "page_updated": pages.get(e["source"], {}).get("updated_time"),
                        "page_og_type": pages.get(e["source"], {}).get("og_type"),
                        "page_unavailable_after": pages.get(e["source"], {}).get("unavailable_after"),
                    }
                    for e in by_target.get(url, [])
                ],
            })

    return {
        "start_url": start_url,
        "base_netloc": base_netloc,
        "crawled_at": datetime.now().isoformat(timespec="seconds"),
        "pages": pages,
        "edges": edges,
        "external_status": external_status,
        "broken": broken,
        "stats": {
            "pages_crawled": len(visited),
            "pages_with_data": len(pages),
            "edges": len(edges),
            "external_targets_checked": len(external_status),
            "broken_count": len(broken),
            "broken_internal": sum(1 for b in broken if b["kind"] == "internal"),
            "broken_external": sum(1 for b in broken if b["kind"] == "external"),
        },
    }


# ---------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------

def write_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_html(data, path):
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TEMPLATE.format(
        start_url=data["start_url"],
        base_netloc=data["base_netloc"],
        pages_crawled=data["stats"]["pages_crawled"],
        edges_count=data["stats"]["edges"],
        broken_count=data["stats"]["broken_count"],
        data_json=data_json,
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def write_broken_report(data, path):
    """Markdown report of broken links, grouped by target."""
    s = data["stats"]
    lines = []
    lines.append("# Broken Links Report")
    lines.append("")
    lines.append(f"- **Site:** {data['start_url']}")
    lines.append(f"- **Crawled:** {data['crawled_at']}")
    lines.append(f"- **Pages crawled:** {s['pages_crawled']}")
    lines.append(f"- **External targets checked:** {s['external_targets_checked']}")
    lines.append(f"- **Total broken:** {s['broken_count']} "
                 f"({s['broken_internal']} internal, {s['broken_external']} external)")
    lines.append("")

    if not data["broken"]:
        lines.append("✅ No broken links found.")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return

    broken_sorted = sorted(
        data["broken"],
        key=lambda b: (b["kind"] != "internal", -len(b["linked_from"]), b["target"]),
    )
    internal = [b for b in broken_sorted if b["kind"] == "internal"]
    external = [b for b in broken_sorted if b["kind"] == "external"]

    def render_section(title, items):
        if not items:
            return
        lines.append(f"## {title}")
        lines.append("")
        for b in items:
            lines.append(f"### `{b['target']}`")
            reason = f"HTTP {b['status']}" if b["status"] else (b["error"] or "unknown error")
            lines.append(f"- **Reason:** {reason}")
            lines.append(f"- **Linked from {len(b['linked_from'])} page(s):**")
            for lf in b["linked_from"][:50]:
                anchor = f' — "{lf["anchor"]}"' if lf["anchor"] else ""
                # Build metadata suffix: updated date, expiration, type
                meta_bits = []
                if lf.get("page_updated"):
                    # Trim ISO timestamp to date for readability
                    date = lf["page_updated"][:10] if len(lf["page_updated"]) >= 10 else lf["page_updated"]
                    meta_bits.append(f"updated {date}")
                if lf.get("page_unavailable_after"):
                    meta_bits.append(f"⏰ expires {lf['page_unavailable_after']}")
                meta_suffix = f" *[{', '.join(meta_bits)}]*" if meta_bits else ""
                lines.append(f"  - `{lf['page']}`{anchor}{meta_suffix}")
            if len(b["linked_from"]) > 50:
                lines.append(f"  - …and {len(b['linked_from']) - 50} more")
            lines.append("")

    render_section("Internal broken pages", internal)
    render_section("External broken links", external)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Simple website link mapper with broken-link detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("url", help="Starting URL (e.g. https://example.com)")
    p.add_argument("--max-pages", type=int, default=100,
                   help="Maximum pages to crawl (default 100)")
    p.add_argument("--delay", type=float, default=0.5,
                   help="Seconds between internal requests (default 0.5)")
    p.add_argument("--external", action="store_true",
                   help="Follow external links during crawl (default: no)")
    p.add_argument("--no-check-external", dest="check_external", action="store_false",
                   help="Skip HEAD-checking external link targets (default: check)")
    p.add_argument("--external-delay", type=float, default=0.1,
                   help="Seconds between external HEAD checks (default 0.1)")
    p.add_argument("--skip-pattern", action="append", default=[],
                   help="Regex pattern of URLs to skip (can be repeated). "
                        "Useful for Drupal admin paths, etc.")
    p.add_argument("--output", default="linkmap",
                   help="Output filename prefix (default 'linkmap')")
    p.add_argument("--timeout", type=int, default=10,
                   help="Request timeout (default 10s)")
    args = p.parse_args()

    try:
        skip_patterns = [re.compile(pattern) for pattern in args.skip_pattern]
    except re.error as e:
        print(f"Invalid --skip-pattern regex: {e}", file=sys.stderr)
        sys.exit(2)

    result = crawl(
        args.url,
        max_pages=args.max_pages,
        delay=args.delay,
        follow_external=args.external,
        timeout=args.timeout,
        skip_patterns=skip_patterns,
        check_external=args.check_external,
        external_delay=args.external_delay,
    )

    write_json(result, f"{args.output}.json")
    print(f"\nWrote {args.output}.json", file=sys.stderr)
    write_html(result, f"{args.output}.html")
    print(f"Wrote {args.output}.html", file=sys.stderr)
    write_broken_report(result, f"{args.output}-broken.md")
    print(f"Wrote {args.output}-broken.md", file=sys.stderr)

    s = result["stats"]
    print(f"\nDone.", file=sys.stderr)
    print(f"  {s['pages_crawled']} pages crawled, "
          f"{s['edges']} edges, "
          f"{s['external_targets_checked']} external targets checked",
          file=sys.stderr)
    if s["broken_count"]:
        print(f"  ⚠ {s['broken_count']} broken target(s): "
              f"{s['broken_internal']} internal, {s['broken_external']} external",
              file=sys.stderr)
    else:
        print("  ✅ No broken links found", file=sys.stderr)


if __name__ == "__main__":
    main()
