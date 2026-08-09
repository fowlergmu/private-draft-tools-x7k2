#!/usr/bin/env python3
"""Build the current fantasy injury snapshot from NFL Daily News on Bluesky."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


HANDLE = "insidenflnews.bsky.social"
API_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
ACTIVE_POSITIONS = {"QB", "RB", "WR", "TE"}
RESOLUTION_TERMS = (
    "activated from", "activated off", "returned to practice", "returns to practice",
    "cleared to play", "cleared for", "full participant", "no limitations",
)
INJURY_TERMS = (
    "injur", "hurt", "limp", "trainer", "medical", "carted", "left practice",
    "missed practice", "misses practice", "missing practice", "did not practice",
    "dnp", "limited practice", "not practicing", "not participating",
    "questionable", "doubtful", "concussion", "contusion", "strain", "sprain",
    "soreness", "discomfort", "surgery", "mri", "undergo tests",
    "day-to-day", "day to day", "week-to-week", "week to week",
    "soft tissue", "without timeline", "expected to return", "ready to play",
    "pup", "nfi", "injured reserve", "placed on ir", "ruled out", "will miss",
) + RESOLUTION_TERMS
BODY_PARTS = (
    ("quad contusion", "Quad contusion"),
    ("high ankle sprain", "High ankle sprain"),
    ("ankle sprain", "Ankle sprain"),
    ("torn acl", "Torn ACL"),
    ("acl", "ACL"),
    ("achilles", "Achilles"),
    ("concussion", "Concussion"),
    ("hamstring", "Hamstring"),
    ("quadriceps", "Quadriceps"),
    ("quad", "Quadriceps"),
    ("groin", "Groin"),
    ("adductor", "Adductor"),
    ("calf", "Calf"),
    ("knee", "Knee"),
    ("ankle", "Ankle"),
    ("foot", "Foot"),
    ("shoulder", "Shoulder"),
    ("neck", "Neck"),
    ("back", "Back"),
    ("hip", "Hip"),
    ("leg", "Leg"),
    ("shin", "Shin"),
    ("wrist", "Wrist"),
    ("hand", "Hand"),
    ("elbow", "Elbow"),
    ("rib", "Rib"),
)
TTL_DAYS = {
    "IR": 60,
    "PUP": 60,
    "NFI": 60,
    "Out": 21,
    "Doubtful": 10,
    "Questionable": 10,
    "Day-to-day": 10,
    "Monitor": 10,
}


@dataclass(frozen=True)
class Player:
    name: str
    pos: str
    rank: int


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_players(path: Path) -> list[Player]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        players = []
        for row in reader:
            name = (row.get("PLAYER NAME") or row.get("name") or "").strip()
            raw_pos = (row.get("POS") or row.get("pos") or "").strip().upper()
            match = re.match(r"[A-Z]+", raw_pos)
            pos = match.group(0) if match else ""
            if not name or pos not in ACTIVE_POSITIONS:
                continue
            try:
                rank = int(row.get("RK") or row.get("rank") or len(players) + 1)
            except ValueError:
                rank = len(players) + 1
            players.append(Player(name=name, pos=pos, rank=rank))
    return players


def player_aliases(players: list[Player]) -> dict[str, Player]:
    aliases: dict[str, list[Player]] = {}
    for player in players:
        full = normalized(player.name)
        variants = {full, re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", full)}
        for alias in variants:
            if len(alias.split()) >= 2:
                aliases.setdefault(alias, []).append(player)
    return {alias: matches[0] for alias, matches in aliases.items() if len(matches) == 1}


def match_players(text: str, aliases: dict[str, Player]) -> list[Player]:
    haystack = " " + normalized(text) + " "
    matches: dict[str, Player] = {}
    for alias, player in aliases.items():
        if " " + alias + " " in haystack:
            matches[player.name] = player
    return sorted(matches.values(), key=lambda player: (-len(normalized(player.name)), player.rank))


def is_injury_post(text: str) -> bool:
    lowered = normalized(text)
    padded = " " + lowered + " "
    for term in INJURY_TERMS:
        needle = normalized(term)
        if term in {"injur", "limp"}:
            if re.search(r"\b" + needle + r"\w*", lowered):
                return True
        elif " " + needle + " " in padded:
            return True
    parentheticals = re.findall(r"\(([^)]+)\)", text)
    return any(
        re.search(r"(?:^| )" + re.escape(normalized(needle)) + r"(?: |$)", normalized(value))
        for value in parentheticals
        for needle, _ in BODY_PARTS
    )


def player_is_subject(text: str, player: Player) -> bool:
    lowered = normalized(text)
    aliases = [normalized(player.name), re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", normalized(player.name))]
    for alias in aliases:
        match = re.search(r"(?:^| )" + re.escape(alias) + r"(?: |$)", lowered)
        if not match:
            continue
        tail = lowered[match.end():].strip()
        if re.match(r"^(said|says|told|discussed)\b", tail):
            return False
        return True
    return False


def classify_status(text: str) -> str:
    lowered = normalized(text)
    if any(normalized(term) in lowered for term in RESOLUTION_TERMS):
        return "Active"
    if "injured reserve" in lowered or "placed on ir" in lowered:
        return "IR"
    if re.search(r"\bpup\b", lowered):
        return "PUP"
    if re.search(r"\bnfi\b", lowered):
        return "NFI"
    if (
        "out for the season" in lowered
        or "season ending" in lowered
        or "ruled out" in lowered
        or re.search(r"\bwill miss\b", lowered)
        or re.search(r"\bout \d+ weeks?\b", lowered)
    ):
        return "Out"
    if "doubtful" in lowered:
        return "Doubtful"
    if "questionable" in lowered:
        return "Questionable"
    if (
        "day to day" in lowered
        or "week to week" in lowered
        or "isn t serious" in lowered
        or "not serious" in lowered
        or re.search(r"\bexpects?\b.*\bback\b.*\bdays?\b", lowered)
        or re.search(r"\b(ok|okay)\b", lowered)
    ):
        return "Day-to-day"
    if (
        re.search(r"\b(miss|missed|misses|missing)\b.*\bpractice\b", lowered)
        or "not practicing" in lowered
        or "not participating" in lowered
    ):
        return "Questionable"
    return "Monitor"


def extract_injury(text: str, player: Player) -> str:
    lowered = normalized(text)
    aliases = [normalized(player.name), re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", normalized(player.name))]
    player_at = min((lowered.find(alias) for alias in aliases if lowered.find(alias) >= 0), default=0)
    context = lowered[player_at:player_at + 180]
    candidates = []
    for needle, label in BODY_PARTS:
        match = re.search(r"(?:^| )" + re.escape(normalized(needle)) + r"(?: |$)", context)
        if match:
            candidates.append((match.start(), label))
    if candidates:
        return min(candidates)[1]
    return "Undisclosed"


def post_url(post: dict) -> str:
    uri = post.get("uri", "")
    rkey = uri.rsplit("/", 1)[-1]
    handle = post.get("author", {}).get("handle") or HANDLE
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def fetch_feed(days: int, now: datetime, limit_pages: int = 6) -> list[dict]:
    cutoff = now - timedelta(days=days)
    cursor = None
    collected: list[dict] = []
    for _ in range(limit_pages):
        params = {"actor": HANDLE, "limit": "100", "filter": "posts_no_replies"}
        if cursor:
            params["cursor"] = cursor
        url = API_URL + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": "private-draft-tools-injury-refresh/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        page = payload.get("feed", [])
        collected.extend(page)
        if not page or not payload.get("cursor"):
            break
        oldest = min(
            (parse_iso(item["post"]["record"]["createdAt"]) for item in page if item.get("post", {}).get("record", {}).get("createdAt")),
            default=now,
        )
        if oldest < cutoff:
            break
        cursor = payload["cursor"]
    return collected


def load_existing(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {
            row["name"]: row
            for row in csv.DictReader(handle)
            if row.get("name") and row.get("status")
        }


def build_snapshot(
    feed: list[dict],
    players: list[Player],
    existing: dict[str, dict[str, str]],
    today: date,
    days: int,
) -> list[dict[str, str]]:
    aliases = player_aliases(players)
    cutoff = datetime.combine(today - timedelta(days=days), datetime.min.time(), tzinfo=timezone.utc)
    newest: dict[str, tuple[datetime, dict[str, str]]] = {}

    for item in feed:
        post = item.get("post", {})
        record = post.get("record", {})
        text = re.sub(r"\s+", " ", record.get("text", "")).strip()
        created_raw = record.get("createdAt", "")
        if not text or not created_raw or not is_injury_post(text):
            continue
        created = parse_iso(created_raw)
        if created < cutoff:
            continue
        for player in match_players(text, aliases):
            if not player_is_subject(text, player):
                continue
            row = {
                "name": player.name,
                "pos": player.pos,
                "status": classify_status(text),
                "injury": extract_injury(text, player),
                "updated": created.date().isoformat(),
                "source": post_url(post),
                "notes": text[:400],
            }
            prior = newest.get(player.name)
            if prior is None or created > prior[0]:
                newest[player.name] = (created, row)

    rank_by_name = {player.name: player.rank for player in players}
    snapshot: dict[str, dict[str, str]] = {}
    for name, row in existing.items():
        try:
            age = (today - date.fromisoformat(row.get("updated", ""))).days
        except ValueError:
            continue
        if age <= TTL_DAYS.get(row.get("status", ""), 0):
            snapshot[name] = row

    for name, (_, row) in newest.items():
        if row["status"] == "Active":
            snapshot.pop(name, None)
        else:
            snapshot[name] = row

    return sorted(snapshot.values(), key=lambda row: (rank_by_name.get(row["name"], 99999), row["name"]))


def write_snapshot(path: Path, rows: list[dict[str, str]], dry_run: bool) -> None:
    fields = ["name", "pos", "status", "injury", "updated", "source", "notes"]
    if dry_run:
        writer = csv.DictWriter(sys.stdout, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rankings", type=Path, default=Path("Data/Tiers.csv"))
    parser.add_argument("--output", type=Path, default=Path("Data/Current Injuries.csv"))
    parser.add_argument("--feed-file", type=Path)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--today", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    players = load_players(args.rankings)
    existing = load_existing(args.output)
    if args.feed_file:
        feed = json.loads(args.feed_file.read_text(encoding="utf-8")).get("feed", [])
    else:
        now = datetime.combine(args.today, datetime.max.time(), tzinfo=timezone.utc)
        feed = fetch_feed(args.days, now)
    rows = build_snapshot(feed, players, existing, args.today, args.days)
    write_snapshot(args.output, rows, args.dry_run)
    print(f"Matched {len(rows)} current fantasy injuries from {len(feed)} feed items.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
