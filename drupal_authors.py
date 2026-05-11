#!/usr/bin/env python3
"""
drupal_authors.py — Enrich linkmap broken-link data with Drupal author info.

For each source page that links to a broken target, looks up:
  * The Drupal node behind that URL (via path translation)
  * The node's author (via JSON:API)

Then writes:
  * <prefix>-with-authors.json  — original data + author info per linked_from
  * <prefix>-broken-by-author.md — broken links grouped by responsible content editor

Requires Drupal 8+ with JSON:API enabled (default in Drupal 11).
Authenticates via username + password (Drupal user with at least
"Use the JSON:API" + "Access user profiles" permissions; admin role works fine).

Env vars (required):
    DRUPAL_URL     base URL of Drupal site (e.g. https://www.example.com)
    DRUPAL_USER    username
    DRUPAL_PASS    password

Usage:
    python drupal_authors.py 3k-fi.json
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests


def login(session, base_url, username, password):
    """Authenticate against Drupal's JSON login endpoint."""
    r = session.post(
        f"{base_url}/user/login?_format=json",
        json={"name": username, "pass": password},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def url_to_node_info(session, base_url, full_url):
    """Resolve a URL to its Drupal node entity info via path translation.

    Drupal exposes /router/translate-path?path=/some/alias which returns the
    canonical entity at that path, including bundle and UUID. Works with path
    aliases and language-prefixed URLs.
    """
    parsed = urlparse(full_url)
    path = parsed.path or "/"

    try:
        r = session.get(
            f"{base_url}/router/translate-path",
            params={"path": path},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        entity = data.get("entity")
        if not entity or entity.get("type") != "node":
            return None
        return {
            "uuid": entity.get("uuid"),
            "id": entity.get("id"),
            "bundle": entity.get("bundle"),
            "label": entity.get("label"),
            "language": data.get("entity", {}).get("langcode") or data.get("language"),
        }
    except Exception as e:
        print(f"    path translate failed for {path}: {e}", file=sys.stderr)
        return None


def get_node_author(session, base_url, bundle, uuid):
    """Fetch node from JSON:API and return author info."""
    try:
        r = session.get(
            f"{base_url}/jsonapi/node/{bundle}/{uuid}",
            params={"include": "uid"},
            headers={"Accept": "application/vnd.api+json"},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json()

        try:
            author_uuid = data["data"]["relationships"]["uid"]["data"]["id"]
        except (KeyError, TypeError):
            return None

        for inc in data.get("included", []):
            if inc.get("type", "").startswith("user--") and inc.get("id") == author_uuid:
                attrs = inc.get("attributes", {})
                return {
                    "uuid": author_uuid,
                    "name": attrs.get("display_name") or attrs.get("name") or "(unknown)",
                    "mail": attrs.get("mail"),
                    "uid": attrs.get("drupal_internal__uid"),
                }
        return {"uuid": author_uuid, "name": "(included data missing)", "mail": None}
    except Exception as e:
        print(f"    JSON:API failed for {bundle}/{uuid}: {e}", file=sys.stderr)
        return None


def write_by_author_report(data, out_path):
    """Markdown report grouping broken links by the responsible content editor."""
    by_author = {}
    no_author = []

    for broken in data.get("broken", []):
        reason = (
            f"HTTP {broken['status']}" if broken.get("status")
            else (broken.get("error") or "unknown")
        )
        for lf in broken.get("linked_from", []):
            entry = {
                "broken_target": broken["target"],
                "source_page": lf["page"],
                "anchor": lf.get("anchor"),
                "reason": reason,
                "node": lf.get("node"),
                "page_updated": lf.get("page_updated"),
                "page_unavailable_after": lf.get("page_unavailable_after"),
                "page_og_type": lf.get("page_og_type"),
            }
            author = lf.get("author")
            if author and author.get("name") not in (None, "(unknown)", "(included data missing)"):
                by_author.setdefault(author["name"], []).append(entry)
            else:
                no_author.append(entry)

    lines = ["# Broken Links by Content Editor", ""]
    lines.append(f"- **Site:** {data.get('start_url', '?')}")
    lines.append(f"- **Crawled:** {data.get('crawled_at', '?')}")
    s = data.get("stats", {})
    lines.append(f"- **Broken targets:** {s.get('broken_count', 0)}")
    lines.append(f"- **Attributed entries:** {sum(len(v) for v in by_author.values())}")
    lines.append(f"- **Unattributed entries:** {len(no_author)}")
    lines.append("")

    if not by_author and not no_author:
        lines.append("✅ No broken-link entries to attribute.")
    else:
        for author_name, entries in sorted(by_author.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"## {author_name} — {len(entries)} entry/entries")
            lines.append("")
            for e in entries:
                anchor = f' — "{e["anchor"]}"' if e["anchor"] else ""
                node_label = (
                    f' — *{e["node"]["label"]}*'
                    if e.get("node") and e["node"].get("label")
                    else ""
                )
                meta_bits = []
                if e.get("page_updated"):
                    date = e["page_updated"][:10] if len(e["page_updated"]) >= 10 else e["page_updated"]
                    meta_bits.append(f"updated {date}")
                if e.get("page_unavailable_after"):
                    meta_bits.append(f"⏰ expires {e['page_unavailable_after']}")
                meta_suffix = f" *[{', '.join(meta_bits)}]*" if meta_bits else ""
                lines.append(f"- **Broken:** `{e['broken_target']}` *({e['reason']})*")
                lines.append(f"  - On page: `{e['source_page']}`{node_label}{anchor}{meta_suffix}")
            lines.append("")

        if no_author:
            lines.append(f"## Unattributed ({len(no_author)} entries)")
            lines.append("")
            lines.append(
                "Source pages whose author couldn't be looked up "
                "(non-Drupal URL, missing permission, or path-translation failed)."
            )
            lines.append("")
            for e in no_author[:50]:
                anchor = f' — "{e["anchor"]}"' if e["anchor"] else ""
                lines.append(f"- **Broken:** `{e['broken_target']}` *({e['reason']})*")
                lines.append(f"  - On page: `{e['source_page']}`{anchor}")
            if len(no_author) > 50:
                lines.append(f"- … and {len(no_author) - 50} more (see JSON for full list)")
            lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python drupal_authors.py <linkmap.json>", file=sys.stderr)
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"Error: {json_path} not found", file=sys.stderr)
        sys.exit(1)

    base_url = os.environ.get("DRUPAL_URL")
    username = os.environ.get("DRUPAL_USER")
    password = os.environ.get("DRUPAL_PASS")

    if not base_url or not username or not password:
        print("Error: set env vars DRUPAL_URL, DRUPAL_USER, DRUPAL_PASS", file=sys.stderr)
        sys.exit(2)

    base_url = base_url.rstrip("/")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    if not data.get("broken"):
        print("No broken links in JSON — nothing to enrich.", file=sys.stderr)
        return

    session = requests.Session()
    session.headers["User-Agent"] = "linkmap-author-lookup/1.0"
    print(f"Authenticating to {base_url}…", file=sys.stderr)
    try:
        login(session, base_url, username, password)
    except Exception as e:
        print(f"Login failed: {e}", file=sys.stderr)
        sys.exit(3)

    # Collect unique source pages from all broken-link referrers
    source_pages = set()
    for broken in data["broken"]:
        for lf in broken.get("linked_from", []):
            # Only Drupal-site URLs
            if base_url.replace("https://", "").replace("http://", "") in lf["page"]:
                source_pages.add(lf["page"])

    print(f"Looking up authors for {len(source_pages)} source page(s)…", file=sys.stderr)

    page_authors = {}
    for i, url in enumerate(sorted(source_pages), 1):
        if i % 10 == 0 or i == len(source_pages):
            print(f"  [{i}/{len(source_pages)}]", file=sys.stderr)
        node = url_to_node_info(session, base_url, url)
        if not node:
            page_authors[url] = None
            continue
        author = get_node_author(session, base_url, node["bundle"], node["uuid"])
        page_authors[url] = {"node": node, "author": author}

    # Inject into broken[].linked_from
    for broken in data["broken"]:
        for lf in broken.get("linked_from", []):
            info = page_authors.get(lf["page"])
            if info:
                lf["node"] = info["node"]
                lf["author"] = info["author"]

    # Outputs
    out_json = json_path.with_name(json_path.stem + "-with-authors.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Wrote {out_json}", file=sys.stderr)

    out_md = json_path.with_name(json_path.stem + "-broken-by-author.md")
    write_by_author_report(data, out_md)
    print(f"Wrote {out_md}", file=sys.stderr)


if __name__ == "__main__":
    main()
