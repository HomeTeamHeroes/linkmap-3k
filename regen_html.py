#!/usr/bin/env python3
"""
regen_html.py — Regenerate the linkmap HTML viewer from existing JSON output.

Use this when you've updated linkmap.py's HTML template (e.g., new viewer
features) and want to refresh an existing crawl's HTML without re-crawling.

Usage:
    py regen_html.py 3k-fi.json
    py regen_html.py 3k-fi.json output.html
"""

import json
import sys
from pathlib import Path

# Import from linkmap.py in the same directory
try:
    from linkmap import write_html
except ImportError:
    print("Error: linkmap.py must be in the same directory as regen_html.py", file=sys.stderr)
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: py regen_html.py <linkmap.json> [output.html]", file=sys.stderr)
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"Error: {json_path} not found", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) > 2:
        out_path = Path(sys.argv[2])
    else:
        out_path = json_path.with_suffix(".html")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    write_html(data, str(out_path))
    print(f"Wrote {out_path}", file=sys.stderr)
    s = data.get("stats", {})
    if s:
        print(f"  {s.get('pages_crawled', '?')} pages, "
              f"{s.get('edges', '?')} edges, "
              f"{s.get('broken_count', 0)} broken", file=sys.stderr)


if __name__ == "__main__":
    main()
