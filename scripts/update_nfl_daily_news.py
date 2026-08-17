#!/usr/bin/env python3
"""Build the current fantasy injury snapshot from FantasyPros and fallbacks."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
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
SLEEPER_API_URL = "https://api.sleeper.app/v1/players/nfl?active=true"
FANTASYPROS_API_URL = "https://api.fantasypros.com/public/v2/json/nfl"
FANTASYPROS_INJURIES_PAGE_URL = "https://www.fantasypros.com/nfl/players/injuries.php"
ACTIVE_POSITIONS = {"QB", "RB", "WR", "TE", "K"}
RESOLUTION_TERMS = (
    "activated from", "activated off", "returned to practice", "returns to practice",
    "cleared to play", "cleared for", "full participant", "practiced in full",
    "removed from the injury report", "no limitations",
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
SLEEPER_TTL_DAYS = {
    "IR": 120,
    "PUP": 120,
    "NFI": 120,
    "Out": 30,
    "Doubtful": 30,
    "Questionable": 30,
}
SLEEPER_STATUS_MAP = {
    "injured reserve": "IR",
    "ir": "IR",
    "pup": "PUP",
    "nfi": "NFI",
    "out": "Out",
    "doubtful": "Doubtful",
    "questionable": "Questionable",
}
FANTASYPROS_STATUS_MAP = {
    "active": "Active",
    "healthy": "Active",
    "full": "Active",
    "full practice": "Active",
    "questionable": "Questionable",
    "doubtful": "Doubtful",
    "out": "Out",
    "injured reserve": "IR",
    "reserve injured": "IR",
    "ir": "IR",
    "physically unable to perform": "PUP",
    "pup": "PUP",
    "non football injury": "NFI",
    "non football illness": "NFI",
    "nfi": "NFI",
    "day to day": "Day-to-day",
    "probable": "Monitor",
}
SOURCE_PRIORITY = {
    "Existing": 0,
    "Sleeper": 100,
    "NFL Daily News": 200,
    "FantasyPros News": 300,
    "FantasyPros Injury Report": 400,
    "Explicit Resolution": 500,
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


def parse_fantasypros_datetime(value: str, fallback: date) -> datetime:
    value = str(value or "").strip()
    if not value:
        return datetime.combine(fallback, datetime.min.time(), tzinfo=timezone.utc)
    try:
        return parse_iso(value)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.combine(fallback, datetime.min.time(), tzinfo=timezone.utc)


def parse_row_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def provider_for(row: dict[str, str]) -> str:
    provider = row.get("provider", "").strip()
    if provider:
        return provider
    source = row.get("source", "")
    if "fantasypros.com" in source:
        return "FantasyPros"
    if "bsky.app" in source:
        return "NFL Daily News"
    if "sleeper" in source:
        return "Sleeper"
    return ""


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def request_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> dict:
    request_headers = {"User-Agent": "private-draft-tools-injury-refresh/2.0"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


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


def indexed_players(players: list[Player]) -> tuple[dict[str, Player], dict[tuple[str, str], Player]]:
    by_name: dict[str, Player] = {}
    by_name_pos: dict[tuple[str, str], Player] = {}
    for player in players:
        variants = {
            normalized(player.name),
            re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", normalized(player.name)),
        }
        for variant in variants:
            by_name.setdefault(variant, player)
            by_name_pos.setdefault((variant, player.pos), player)
    return by_name, by_name_pos


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
    aliases = [normalized(player.name), re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", normalized(player.name))]
    segments = re.split(r"(?<=[.!?])\s+|\s*[|\u2022]\s*", clean_text(text))
    for segment in segments:
        lowered = normalized(segment)
        for alias in aliases:
            for match in re.finditer(r"(?:^| )" + re.escape(alias) + r"(?: |$)", lowered):
                before = lowered[:match.start()].strip()
                after = lowered[match.end():].strip()
                if re.match(r"^(said|says|told|discussed)\b", after):
                    continue
                if is_injury_post(after[:180]):
                    return True
                if (
                    is_injury_post(before[-120:])
                    and not re.search(r"\b(and|with|against|from|by|to|for|of)$", before)
                ):
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


def fetch_sleeper_players() -> dict[str, dict]:
    return request_json(SLEEPER_API_URL, timeout=45)


def fetch_fantasypros_injuries(api_key: str, season: int) -> dict:
    headers = {"x-api-key": api_key}
    injury_query = urllib.parse.urlencode({
        "year": str(season),
        "include_probabilities": "true",
    })
    return request_json(f"{FANTASYPROS_API_URL}/injuries?{injury_query}", headers)


def fetch_fantasypros_news(api_key: str) -> dict:
    headers = {"x-api-key": api_key}
    news_query = urllib.parse.urlencode({
        "limit": "100",
        "category": "injury",
        "order_by": "updated",
    })
    return request_json(f"{FANTASYPROS_API_URL}/news?{news_query}", headers)


def build_sleeper_rows(
    payload: dict[str, dict],
    players: list[Player],
    today: date,
) -> list[dict[str, str]]:
    index: dict[str, dict] = {}
    for sleeper_player in payload.values():
        full_name = (sleeper_player.get("full_name") or "").strip()
        if not full_name:
            first = (sleeper_player.get("first_name") or "").strip()
            last = (sleeper_player.get("last_name") or "").strip()
            full_name = f"{first} {last}".strip()
        key = normalized(full_name)
        if key:
            index[key] = sleeper_player
            index.setdefault(re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", key), sleeper_player)

    rows = []
    for player in players:
        key = normalized(player.name)
        sleeper_player = index.get(key) or index.get(re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", key))
        if not sleeper_player:
            continue
        raw_status = normalized(str(sleeper_player.get("injury_status") or ""))
        status = SLEEPER_STATUS_MAP.get(raw_status)
        if not status:
            continue
        try:
            updated_at = datetime.fromtimestamp(int(sleeper_player["news_updated"]) / 1000, tz=timezone.utc)
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if (today - updated_at.date()).days > SLEEPER_TTL_DAYS[status]:
            continue
        injury = (sleeper_player.get("injury_body_part") or "Undisclosed").strip()
        practice = (sleeper_player.get("practice_participation") or "").strip()
        details = [f"Sleeper lists {player.name} as {status}."]
        if practice:
            details.append(f"Practice: {practice}.")
        rows.append({
            "name": player.name,
            "pos": player.pos,
            "status": status,
            "injury": injury,
            "updated": updated_at.date().isoformat(),
            "source": SLEEPER_API_URL,
            "provider": "Sleeper",
            "notes": " ".join(details),
        })
    return rows


def fantasypros_status(item: dict) -> str | None:
    raw_status = normalized(str(item.get("status") or item.get("injury_status") or ""))
    status = FANTASYPROS_STATUS_MAP.get(raw_status)
    if status:
        return status

    practices = [
        normalized(str(item.get(f"practice_{number}") or ""))
        for number in (1, 2, 3)
        if item.get(f"practice_{number}")
    ]
    if not practices:
        return None
    latest = practices[-1]
    if latest in {"full", "full practice", "full participation"}:
        return "Active"
    if latest in {"dnp", "did not practice", "did not participate"}:
        return "Questionable"
    if latest in {"limit", "limited", "limited practice", "limited participation"}:
        return "Monitor"
    return None


def match_ranked_player(
    item: dict,
    by_name: dict[str, Player],
    by_name_pos: dict[tuple[str, str], Player],
) -> Player | None:
    name = str(item.get("name") or item.get("player_name") or "").strip()
    pos = str(item.get("position_id") or item.get("position") or "").strip().upper()
    key = normalized(name)
    suffixless = re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", key)
    if pos:
        return by_name_pos.get((key, pos)) or by_name_pos.get((suffixless, pos))
    return by_name.get(key) or by_name.get(suffixless)


def build_fantasypros_injury_candidates(
    payload: dict,
    players: list[Player],
    today: date,
) -> tuple[list[tuple[datetime, int, dict[str, str]]], dict[int, Player]]:
    by_name, by_name_pos = indexed_players(players)
    candidates: list[tuple[datetime, int, dict[str, str]]] = []
    player_ids: dict[int, Player] = {}

    for item in payload.get("injuries", []):
        if not isinstance(item, dict):
            continue
        player = match_ranked_player(item, by_name, by_name_pos)
        if not player:
            continue
        try:
            player_id = int(item.get("player_id"))
        except (TypeError, ValueError):
            player_id = 0
        if player_id:
            player_ids[player_id] = player

        status = fantasypros_status(item)
        if not status:
            continue
        observed_at = parse_fantasypros_datetime(item.get("injury_update_date", ""), today)
        injury = clean_text(
            item.get("injury_type")
            or item.get("practice_report_injury_type")
            or "Undisclosed"
        )
        practices = [
            clean_text(item.get(f"practice_{number}", ""))
            for number in (1, 2, 3)
            if item.get(f"practice_{number}")
        ]
        notes = clean_text(item.get("comment", ""))
        details = [notes] if notes else [f"FantasyPros lists {player.name} as {status}."]
        if practices:
            details.append("Practice reports: " + " / ".join(practices) + ".")
        probability = str(item.get("probability_of_playing") or "").strip()
        if probability:
            try:
                details.append(f"Listed probability of playing: {float(probability):.0%}.")
            except ValueError:
                pass
        source = clean_text(item.get("link") or item.get("url") or item.get("filename"))
        if not source.startswith("http"):
            source = FANTASYPROS_INJURIES_PAGE_URL
        row = {
            "name": player.name,
            "pos": player.pos,
            "status": status,
            "injury": injury or "Undisclosed",
            "updated": observed_at.date().isoformat(),
            "source": source,
            "provider": "FantasyPros Injury Report",
            "notes": " ".join(details)[:400],
        }
        candidates.append((observed_at, SOURCE_PRIORITY[row["provider"]], row))
    return candidates, player_ids


def build_fantasypros_news_candidates(
    payload: dict,
    players: list[Player],
    today: date,
    days: int,
    player_ids: dict[int, Player] | None = None,
) -> list[tuple[datetime, int, dict[str, str]]]:
    aliases = player_aliases(players)
    cutoff = datetime.combine(today - timedelta(days=days), datetime.min.time(), tzinfo=timezone.utc)
    newest: dict[str, tuple[datetime, int, dict[str, str]]] = {}
    player_ids = player_ids or {}

    for item in payload.get("items", []):
        if not isinstance(item, dict):
            continue
        observed_at = parse_fantasypros_datetime(
            item.get("updated") or item.get("created") or "",
            today,
        )
        if observed_at < cutoff:
            continue
        text = clean_text(" ".join(
            str(item.get(field) or "") for field in ("title", "desc", "impact")
        ))
        if not text:
            continue
        try:
            explicit_player = player_ids.get(int(item.get("player_id")))
        except (TypeError, ValueError):
            explicit_player = None
        matches = [explicit_player] if explicit_player else match_players(text, aliases)
        for player in (candidate for candidate in matches if candidate):
            if not explicit_player and not player_is_subject(text, player):
                continue
            status = classify_status(text)
            source = clean_text(item.get("link") or FANTASYPROS_INJURIES_PAGE_URL)
            row = {
                "name": player.name,
                "pos": player.pos,
                "status": status,
                "injury": extract_injury(text, player),
                "updated": observed_at.date().isoformat(),
                "source": source if source.startswith("http") else FANTASYPROS_INJURIES_PAGE_URL,
                "provider": "FantasyPros News",
                "notes": text[:400],
            }
            priority = (
                SOURCE_PRIORITY["Explicit Resolution"]
                if status == "Active"
                else SOURCE_PRIORITY[row["provider"]]
            )
            candidate = (observed_at, priority, row)
            prior = newest.get(player.name)
            if prior is None or candidate[:2] > prior[:2]:
                newest[player.name] = candidate
    return list(newest.values())


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
    sleeper_payload: dict[str, dict] | None = None,
    fantasypros_injuries: dict | None = None,
    fantasypros_news: dict | None = None,
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
                "provider": "NFL Daily News",
                "notes": text[:400],
            }
            prior = newest.get(player.name)
            if prior is None or created > prior[0]:
                newest[player.name] = (created, row)

    rank_by_name = {player.name: player.rank for player in players}
    snapshot: dict[str, dict[str, str]] = {}
    snapshot_meta: dict[str, tuple[date, int, datetime]] = {}
    for name, row in existing.items():
        try:
            age = (today - date.fromisoformat(row.get("updated", ""))).days
        except ValueError:
            continue
        if age <= TTL_DAYS.get(row.get("status", ""), 0):
            snapshot[name] = {**row, "provider": provider_for(row)}
            observed = parse_fantasypros_datetime(row.get("updated", ""), today)
            snapshot_meta[name] = (observed.date(), SOURCE_PRIORITY["Existing"], observed)

    candidates: list[tuple[datetime, int, dict[str, str]]] = []
    candidates.extend(
        (
            observed_at,
            SOURCE_PRIORITY["Explicit Resolution"]
            if row["status"] == "Active"
            else SOURCE_PRIORITY["NFL Daily News"],
            row,
        )
        for observed_at, row in newest.values()
    )
    for row in build_sleeper_rows(sleeper_payload or {}, players, today):
        observed_at = parse_fantasypros_datetime(row["updated"], today)
        candidates.append((observed_at, SOURCE_PRIORITY["Sleeper"], row))

    fp_injury_candidates, fp_player_ids = build_fantasypros_injury_candidates(
        fantasypros_injuries or {}, players, today
    )
    candidates.extend(fp_injury_candidates)
    candidates.extend(build_fantasypros_news_candidates(
        fantasypros_news or {}, players, today, days, fp_player_ids
    ))

    for observed_at, priority, row in sorted(
        candidates, key=lambda item: (item[0].date(), item[1], item[0])
    ):
        name = row["name"]
        candidate_key = (observed_at.date(), priority, observed_at)
        if candidate_key < snapshot_meta.get(
            name,
            (date.min, -1, datetime.min.replace(tzinfo=timezone.utc)),
        ):
            continue
        current = snapshot.get(name)
        merged = row.copy()
        current_provider = provider_for(current or {})
        incoming_provider = provider_for(row)
        if current and incoming_provider == "Sleeper" and "NFL Daily News" in current_provider:
            merged["source"] = current.get("source", merged["source"])
            merged["notes"] = current.get("notes", merged["notes"])
            merged["provider"] = "Sleeper + NFL Daily News"
        elif current and incoming_provider == "FantasyPros Injury Report" and current_provider in {
            "FantasyPros News", "NFL Daily News"
        }:
            merged["source"] = current.get("source", merged["source"])
            merged["notes"] = current.get("notes", merged["notes"])
            merged["provider"] = f"FantasyPros Injury Report + {current_provider}"

        snapshot_meta[name] = candidate_key
        if merged["status"] == "Active":
            snapshot.pop(name, None)
        else:
            snapshot[name] = merged

    return sorted(snapshot.values(), key=lambda row: (rank_by_name.get(row["name"], 99999), row["name"]))


def write_snapshot(path: Path, rows: list[dict[str, str]], dry_run: bool) -> None:
    fields = ["name", "pos", "status", "injury", "updated", "source", "provider", "notes"]
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
    parser.add_argument("--kickers", type=Path, default=Path("Data/Kickers.csv"))
    parser.add_argument("--output", type=Path, default=Path("Data/Current Injuries.csv"))
    parser.add_argument("--feed-file", type=Path)
    parser.add_argument("--sleeper-file", type=Path)
    parser.add_argument("--fantasypros-injuries-file", type=Path)
    parser.add_argument("--fantasypros-news-file", type=Path)
    parser.add_argument("--season", type=int)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--today", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    players = load_players(args.rankings)
    if args.kickers.exists():
        players.extend(load_players(args.kickers))
    existing = load_existing(args.output)
    source_status: list[str] = []
    structured_sources: list[str] = []

    if args.feed_file:
        feed = json.loads(args.feed_file.read_text(encoding="utf-8")).get("feed", [])
        source_status.append("Bluesky fixture")
    else:
        now = datetime.combine(args.today, datetime.max.time(), tzinfo=timezone.utc)
        try:
            feed = fetch_feed(args.days, now)
            source_status.append("NFL Daily News")
        except Exception as exc:
            feed = []
            print(f"Warning: NFL Daily News unavailable: {exc}", file=sys.stderr)

    if args.sleeper_file:
        sleeper_payload = json.loads(args.sleeper_file.read_text(encoding="utf-8"))
        source_status.append("Sleeper fixture")
        structured_sources.append("Sleeper")
    else:
        try:
            sleeper_payload = fetch_sleeper_players()
            source_status.append("Sleeper")
            structured_sources.append("Sleeper")
        except Exception as exc:
            sleeper_payload = {}
            print(f"Warning: Sleeper unavailable: {exc}", file=sys.stderr)

    fp_injuries: dict = {}
    fp_news: dict = {}
    if args.fantasypros_injuries_file or args.fantasypros_news_file:
        if not (args.fantasypros_injuries_file and args.fantasypros_news_file):
            parser.error("FantasyPros fixture runs require both injury and news files")
        fp_injuries = json.loads(args.fantasypros_injuries_file.read_text(encoding="utf-8"))
        fp_news = json.loads(args.fantasypros_news_file.read_text(encoding="utf-8"))
        source_status.append("FantasyPros fixtures")
        structured_sources.append("FantasyPros")
    else:
        api_key = os.environ.get("FANTASYPROS_API_KEY", "").strip()
        if api_key:
            season = args.season or (args.today.year if args.today.month >= 3 else args.today.year - 1)
            try:
                fp_injuries = fetch_fantasypros_injuries(api_key, season)
                source_status.append("FantasyPros injuries")
                structured_sources.append("FantasyPros")
            except Exception as exc:
                print(f"Warning: FantasyPros injuries unavailable: {exc}", file=sys.stderr)
            try:
                fp_news = fetch_fantasypros_news(api_key)
                source_status.append("FantasyPros news")
            except Exception as exc:
                print(f"Warning: FantasyPros news unavailable: {exc}", file=sys.stderr)
        else:
            print(
                "FantasyPros skipped: add the FANTASYPROS_API_KEY repository secret to enable it.",
                file=sys.stderr,
            )

    if not structured_sources:
        print("No structured injury source was available; leaving the snapshot unchanged.", file=sys.stderr)
        return 1

    rows = build_snapshot(
        feed,
        players,
        existing,
        args.today,
        args.days,
        sleeper_payload,
        fp_injuries,
        fp_news,
    )
    write_snapshot(args.output, rows, args.dry_run)
    print(
        f"Matched {len(rows)} current fantasy injuries using {', '.join(source_status)} "
        f"({len(feed)} Bluesky items, {len(sleeper_payload)} Sleeper players, "
        f"{len(fp_injuries.get('injuries', []))} FantasyPros injuries, "
        f"{len(fp_news.get('items', []))} FantasyPros news items).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
