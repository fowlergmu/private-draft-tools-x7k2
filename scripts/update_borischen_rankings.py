#!/usr/bin/env python3
"""Rebuild the draft pool from Boris Chen's public Full-PPR tier feeds."""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import subprocess
import tempfile
import unicodedata
import urllib.request
from urllib.error import URLError
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path


OVERALL_URLS = (
    "https://s3-us-west-1.amazonaws.com/fftiers/out/text_ALL-PPR-adjust0.txt",
    "https://s3-us-west-1.amazonaws.com/fftiers/out/text_ALL-PPR-adjust1.txt",
    "https://s3-us-west-1.amazonaws.com/fftiers/out/text_ALL-PPR-adjust2.txt",
)
KICKER_URL = "https://s3-us-west-1.amazonaws.com/fftiers/out/text_K.txt"
DST_URL = "https://s3-us-west-1.amazonaws.com/fftiers/out/text_DST.txt"
RANKING_HEADERS = [
    "RK", "TIERS", "PLAYER NAME", "TEAM", "POS", "BYE WEEK",
    "UPSIDE", "BUST", "SOS SEASON", "ECR VS. ADP",
]
KICKER_HEADERS = [
    "name", "pos", "tier", "rank", "adp", "team", "bye", "floor",
    "ceiling", "source_rank", "source_updated",
]
SUPPORTED_POSITIONS = {"QB", "RB", "WR", "TE", "DST"}


@dataclass(frozen=True)
class TierEntry:
    name: str
    tier: int
    rank: int


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def name_variants(value: str) -> set[str]:
    full = normalized(value)
    return {full, re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", full)}


def parse_tier_texts(texts: list[str], *, minimum: int, maximum: int) -> list[TierEntry]:
    entries: list[TierEntry] = []
    expected_tier = 1
    for text in texts:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = re.fullmatch(r"Tier\s+(\d+):\s*(.+)", line)
            if not match:
                raise ValueError(f"Unrecognized Boris Chen tier row: {line[:100]}")
            tier = int(match.group(1))
            if tier != expected_tier:
                raise ValueError(f"Expected Tier {expected_tier}, found Tier {tier}")
            names = [name.strip() for name in match.group(2).split(",") if name.strip()]
            if not names:
                raise ValueError(f"Tier {tier} has no players")
            for name in names:
                entries.append(TierEntry(name=name, tier=tier, rank=len(entries) + 1))
            expected_tier += 1

    if not minimum <= len(entries) <= maximum:
        raise ValueError(
            f"Boris Chen feed has {len(entries)} players; expected {minimum}-{maximum}"
        )
    keys = [normalized(entry.name) for entry in entries]
    if len(keys) != len(set(keys)):
        duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
        raise ValueError(f"Duplicate players in Boris Chen feed: {', '.join(duplicates)}")
    return entries


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def player_index(rows: list[dict[str, str]], name_field: str) -> dict[str, dict[str, str]]:
    candidates: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        for variant in name_variants(row.get(name_field, "")):
            if variant:
                candidates.setdefault(variant, []).append(row)
    return {key: matches[0] for key, matches in candidates.items() if len(matches) == 1}


def match_row(entry: TierEntry, index: dict[str, dict[str, str]]) -> dict[str, str] | None:
    for variant in name_variants(entry.name):
        if variant in index:
            return index[variant]
    return None


def base_position(value: str) -> str:
    match = re.match(r"[A-Z]+", value.upper().strip())
    return match.group(0) if match else ""


def old_adp(row: dict[str, str]) -> float | None:
    try:
        rank = float(row["RK"])
        delta = float(row["ECR VS. ADP"].replace("+", ""))
    except (KeyError, TypeError, ValueError):
        return None
    return rank + delta


def format_delta(adp: float | None, rank: int) -> str:
    if adp is None:
        return "-"
    delta = adp - rank
    if abs(delta - round(delta)) < 0.001:
        value = str(int(round(delta)))
    else:
        value = f"{delta:.1f}".rstrip("0").rstrip(".")
    return f"+{value}" if delta > 0 else value


def build_rankings(
    overall: list[TierEntry],
    dst: list[TierEntry],
    existing_rows: list[dict[str, str]],
    kicker_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    main_index = player_index(existing_rows, "PLAYER NAME")
    kicker_index = player_index(kicker_rows, "name")
    selected: list[tuple[int, int, TierEntry, dict[str, str]]] = []
    included_names: set[str] = set()
    unmatched: list[str] = []

    for entry in overall:
        row = match_row(entry, main_index)
        if row is None:
            if match_row(entry, kicker_index) is None:
                unmatched.append(entry.name)
            continue
        position = base_position(row.get("POS", ""))
        if position not in SUPPORTED_POSITIONS:
            raise ValueError(f"Unsupported position for {entry.name}: {row.get('POS', '')}")
        selected.append((entry.rank, entry.tier, entry, row))
        included_names.add(normalized(row["PLAYER NAME"]))

    next_rank = len(overall) + 1
    overall_max_tier = max(entry.tier for entry in overall)
    extra_dst_tiers: dict[int, int] = {}
    for entry in dst:
        row = match_row(entry, main_index)
        if row is None:
            unmatched.append(entry.name)
            continue
        key = normalized(row["PLAYER NAME"])
        if key in included_names:
            continue
        if base_position(row.get("POS", "")) != "DST":
            raise ValueError(f"Defense feed matched non-DST player: {entry.name}")
        if entry.tier not in extra_dst_tiers:
            extra_dst_tiers[entry.tier] = overall_max_tier + len(extra_dst_tiers) + 1
        selected.append((next_rank, extra_dst_tiers[entry.tier], entry, row))
        included_names.add(key)
        next_rank += 1

    if unmatched:
        raise ValueError("Missing metadata for Boris Chen players: " + ", ".join(unmatched))

    position_counts: Counter[str] = Counter()
    output: list[dict[str, str]] = []
    for rank, tier, entry, old in selected:
        position = base_position(old["POS"])
        position_counts[position] += 1
        output.append({
            "RK": str(rank),
            "TIERS": str(tier),
            "PLAYER NAME": entry.name,
            "TEAM": old["TEAM"],
            "POS": f"{position}{position_counts[position]}",
            "BYE WEEK": old["BYE WEEK"],
            "UPSIDE": old["UPSIDE"],
            "BUST": old["BUST"],
            "SOS SEASON": old["SOS SEASON"],
            "ECR VS. ADP": format_delta(old_adp(old), rank),
        })

    minimums = {"QB": 20, "RB": 50, "WR": 60, "TE": 20, "DST": 20}
    failures = [
        f"{position}={position_counts[position]} (<{minimum})"
        for position, minimum in minimums.items()
        if position_counts[position] < minimum
    ]
    if failures or len(output) < 200:
        raise ValueError("Incomplete draft pool: " + ", ".join(failures or [str(len(output))]))
    return output


def build_kickers(
    entries: list[TierEntry],
    existing_rows: list[dict[str, str]],
    updated: date,
) -> tuple[list[dict[str, str]], list[str]]:
    index = player_index(existing_rows, "name")
    output: list[dict[str, str]] = []
    unmatched: list[str] = []
    for entry in entries:
        old = match_row(entry, index)
        if old is None:
            unmatched.append(entry.name)
            continue
        source_rank = len(output) + 1
        output.append({
            "name": entry.name,
            "pos": "K",
            "tier": str(entry.tier),
            "rank": str(180 + source_rank),
            "adp": old["adp"],
            "team": old["team"],
            "bye": old["bye"],
            "floor": old["floor"],
            "ceiling": old["ceiling"],
            "source_rank": str(source_rank),
            "source_updated": updated.isoformat(),
        })
    if len(output) < 16:
        raise ValueError(f"Only {len(output)} Boris Chen kickers matched existing metadata")
    existing_keys = {normalized(row["name"]) for row in existing_rows}
    output_keys = {normalized(row["name"]) for row in output}
    if existing_keys - output_keys:
        raise ValueError("Existing kickers missing from Boris Chen feed")
    return output, unmatched


def serialize_csv(headers: list[str], rows: list[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n", quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def write_if_changed(path: Path, content: str, check: bool) -> bool:
    current = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    if current.replace("\r\n", "\n") == content:
        return False
    if check:
        return True
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.replace(temporary, path)
    return True


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "private-draft-tools-borischen/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except URLError as error:
        fallback = subprocess.run(
            ["curl", "-fsSL", url],
            check=False,
            capture_output=True,
            text=True,
            timeout=35,
        )
        if fallback.returncode != 0:
            raise RuntimeError(
                f"Could not fetch {url}: {fallback.stderr.strip()}"
            ) from error
        return fallback.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rankings", type=Path, default=Path("Data/Tiers.csv"))
    parser.add_argument("--kickers", type=Path, default=Path("Data/Kickers.csv"))
    parser.add_argument("--fixture-dir", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    ranking_headers, existing_rankings = read_csv(args.rankings)
    kicker_headers, existing_kickers = read_csv(args.kickers)
    if ranking_headers != RANKING_HEADERS:
        raise ValueError(f"Unexpected rankings headers: {ranking_headers}")
    if kicker_headers != KICKER_HEADERS:
        raise ValueError(f"Unexpected kicker headers: {kicker_headers}")

    if args.fixture_dir:
        overall_texts = [
            (args.fixture_dir / f"overall-{index}.txt").read_text(encoding="utf-8")
            for index in range(3)
        ]
        kicker_text = (args.fixture_dir / "kickers.txt").read_text(encoding="utf-8")
        dst_text = (args.fixture_dir / "dst.txt").read_text(encoding="utf-8")
    else:
        overall_texts = [fetch_text(url) for url in OVERALL_URLS]
        kicker_text = fetch_text(KICKER_URL)
        dst_text = fetch_text(DST_URL)

    overall = parse_tier_texts(overall_texts, minimum=195, maximum=205)
    kickers = parse_tier_texts([kicker_text], minimum=18, maximum=25)
    defenses = parse_tier_texts([dst_text], minimum=18, maximum=25)
    rankings_output = build_rankings(overall, defenses, existing_rankings, existing_kickers)
    kickers_output, unmatched_kickers = build_kickers(kickers, existing_kickers, date.today())

    ranking_changed = write_if_changed(
        args.rankings, serialize_csv(RANKING_HEADERS, rankings_output), args.check
    )
    kicker_changed = write_if_changed(
        args.kickers, serialize_csv(KICKER_HEADERS, kickers_output), args.check
    )
    positions = Counter(base_position(row["POS"]) for row in rankings_output)
    print(
        f"Boris Chen Full-PPR: {len(overall)} overall players across "
        f"{max(entry.tier for entry in overall)} tiers; output {len(rankings_output)} rankings "
        f"({', '.join(f'{key} {positions[key]}' for key in ('QB', 'RB', 'WR', 'TE', 'DST'))}) "
        f"and {len(kickers_output)} kickers."
    )
    if unmatched_kickers:
        print("Kickers without existing site metadata (skipped): " + ", ".join(unmatched_kickers))
    print(
        "Changes: "
        f"Tiers.csv={'yes' if ranking_changed else 'no'}, "
        f"Kickers.csv={'yes' if kicker_changed else 'no'}"
    )
    return 1 if args.check and (ranking_changed or kicker_changed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
