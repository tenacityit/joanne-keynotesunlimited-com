#!/usr/bin/env python3
"""Pull Joanne's picked podcast episodes into data/feeds.json.

Run on a schedule by .github/workflows/update-feeds.yml. Standard library only.
"""
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

PODCAST_FEED = "https://media.rss.com/smiklespeaks/feed.xml"
PICKED_EPISODES = [  # Joanne's hand-picked episodes, shown in this order (exact feed titles)
    "Courageous Leadership",
    "How Leaders Create Conflict",
    "Resilience is not...",
]
OUT = Path(__file__).resolve().parent.parent / "data" / "feeds.json"

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "keynotesunlimited-feed-bot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def clean(text, limit=240):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def podcast():
    ch = ET.fromstring(fetch(PODCAST_FEED)).find("channel")
    img = ch.find("itunes:image", NS)
    items = {it.findtext("title"): it for it in ch.findall("item")}
    missing = [t for t in PICKED_EPISODES if t not in items]
    if missing:
        raise RuntimeError(f"picked episodes not in feed: {missing}")
    episodes = []
    for it in (items[t] for t in PICKED_EPISODES):
        enc = it.find("enclosure")
        episodes.append({
            "title": it.findtext("title"),
            "published": parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc).isoformat(),
            "link": it.findtext("link"),
            "audio": enc.get("url") if enc is not None else None,
            "duration": it.findtext("itunes:duration", namespaces=NS),
            "summary": clean(it.findtext("description")),
        })
    return {
        "title": ch.findtext("title"),
        "link": ch.findtext("link"),
        "image": img.get("href") if img is not None else None,
        "episodeCount": len(ch.findall("item")),
        "episodes": episodes,
    }


def main():
    data = {"podcast": {}}
    errors = []
    for key, fn in (("podcast", podcast),):
        try:
            data[key] = fn()
        except Exception as exc:  # keep the previous data for a feed that fails
            errors.append(f"{key}: {exc}")
    if errors and OUT.exists():
        old = json.loads(OUT.read_text())
        for key in ("podcast",):
            if not data[key]:
                data[key] = old.get(key, data[key])
    if not data["podcast"]:
        print("podcast feed failed:", *errors, sep="\n", file=sys.stderr)
        sys.exit(1)
    OUT.parent.mkdir(exist_ok=True)
    if OUT.exists():
        old = json.loads(OUT.read_text())
        old.pop("updated", None)
        if old == data:  # nothing new: leave the file (and git history) alone
            print("no changes", *errors)
            return
    data["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}: {len(data['podcast'].get('episodes', []))} episodes", *errors)


if __name__ == "__main__":
    main()
