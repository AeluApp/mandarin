#!/usr/bin/env python3
"""Media catalog URL health checker.

Checks all media URLs for accessibility. Run periodically to detect
deprecated/removed content that needs replacement.

Usage:
    python tools/media_health.py              # Check all URLs
    python tools/media_health.py --fix        # Check and report fixable issues
    python tools/media_health.py --json       # Output JSON report
"""
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

CATALOG_PATH = Path(__file__).parent.parent / "data" / "media_catalog.json"
HEALTH_LOG = Path(__file__).parent.parent / "data" / "media_health.json"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
TIMEOUT = 15


def check_url(url: str) -> dict:
    """Check a single URL and return status dict."""
    if not url:
        return {"status": "missing", "error": "No URL"}

    if any(k in url.lower() for k in ("/search", "/results?", "keyword=")):
        return {"status": "search_url", "error": "Search page, not direct content"}

    try:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        return {"status": "ok", "http_code": resp.status}
    except urllib.error.HTTPError as e:
        # 400/403/405 from streaming sites are false positives (anti-bot)
        if e.code in (400, 403, 405):
            return {"status": "ok_restricted", "http_code": e.code,
                    "note": "Blocked by anti-bot but likely valid"}
        return {"status": "broken", "http_code": e.code, "error": str(e.reason)}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


def check_youtube_oembed(video_id: str) -> dict:
    """Verify YouTube video exists via oEmbed API."""
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        data = json.loads(resp.read())
        return {"status": "ok", "title": data.get("title", ""),
                "channel": data.get("author_name", "")}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": "removed", "error": "Video no longer exists"}
        return {"status": "error", "http_code": e.code}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


def run_health_check(output_json=False):
    """Run full health check on all media catalog entries."""
    with open(CATALOG_PATH) as f:
        catalog = json.load(f)

    entries = catalog.get("entries", [])
    results = []
    counters = {"ok": 0, "ok_restricted": 0, "broken": 0, "search_url": 0,
                "missing": 0, "error": 0, "removed": 0}

    for i, entry in enumerate(entries):
        eid = entry.get("id", f"unknown_{i}")
        url = entry.get("url", "")
        title = entry.get("title", "")

        # For YouTube URLs, use oEmbed for more accurate checking
        if "youtube.com/watch?v=" in url:
            vid = url.split("v=")[1].split("&")[0]
            result = check_youtube_oembed(vid)
        else:
            result = check_url(url)

        result["id"] = eid
        result["title"] = title
        result["url"] = url
        result["hsk_level"] = entry.get("hsk_level", 0)
        results.append(result)

        status = result["status"]
        counters[status] = counters.get(status, 0) + 1

        if not output_json:
            icon = {"ok": "✓", "ok_restricted": "~", "broken": "✗",
                    "search_url": "?", "missing": "!", "error": "⚠",
                    "removed": "✗"}.get(status, "?")
            if status in ("broken", "removed", "error", "search_url", "missing"):
                print(f"  {icon} [{status:14s}] {eid}: {result.get('error', '')}")

    # Save health log
    log = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total": len(entries),
        "counters": counters,
        "issues": [r for r in results if r["status"] not in ("ok", "ok_restricted")],
    }
    with open(HEALTH_LOG, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    if output_json:
        print(json.dumps(log, indent=2, ensure_ascii=False))
    else:
        print(f"\n  Media Health Report ({log['checked_at'][:10]})")
        print(f"  {'─' * 40}")
        print(f"  Total entries:     {len(entries)}")
        print(f"  OK:                {counters['ok']}")
        print(f"  OK (restricted):   {counters['ok_restricted']}")
        print(f"  Broken/removed:    {counters['broken'] + counters['removed']}")
        print(f"  Search URLs:       {counters['search_url']}")
        print(f"  Missing:           {counters['missing']}")
        print(f"  Errors:            {counters['error']}")
        print()

        if counters["broken"] + counters["removed"] + counters["search_url"] > 0:
            print("  Action needed: replace broken/search entries with specific video URLs")
            print(f"  Full report saved to: {HEALTH_LOG}")
        else:
            print("  All URLs healthy.")

    return log


if __name__ == "__main__":
    output_json = "--json" in sys.argv
    run_health_check(output_json=output_json)
