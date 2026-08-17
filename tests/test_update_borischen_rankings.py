import sys
import unittest
from datetime import date
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_borischen_rankings as updater


class BorisChenRankingTests(unittest.TestCase):
    def test_parses_sequential_tiers_across_chunks(self):
        entries = updater.parse_tier_texts(
            ["Tier 1: Alpha One, Beta Two\n", "Tier 2: Gamma Three\n"],
            minimum=3,
            maximum=3,
        )
        self.assertEqual(
            [(entry.rank, entry.tier, entry.name) for entry in entries],
            [(1, 1, "Alpha One"), (2, 1, "Beta Two"), (3, 2, "Gamma Three")],
        )

    def test_rejects_missing_tier(self):
        with self.assertRaisesRegex(ValueError, "Expected Tier 2"):
            updater.parse_tier_texts(
                ["Tier 1: Alpha One\nTier 3: Beta Two\n"], minimum=2, maximum=2
            )

    def test_rejects_duplicate_player(self):
        with self.assertRaisesRegex(ValueError, "Duplicate players"):
            updater.parse_tier_texts(
                ["Tier 1: Alpha One\nTier 2: Alpha One\n"], minimum=2, maximum=2
            )

    def test_recomputes_adp_difference_from_boris_rank(self):
        row = {"RK": "10", "ECR VS. ADP": "+5"}
        self.assertEqual(updater.format_delta(updater.old_adp(row), 7), "+8")

    def test_public_feed_fixture_is_complete(self):
        root = Path(__file__).resolve().parents[1]
        fixture = root / "tests" / "fixtures" / "borischen"
        overall = updater.parse_tier_texts(
            [(fixture / f"overall-{index}.txt").read_text() for index in range(3)],
            minimum=195,
            maximum=205,
        )
        dst = updater.parse_tier_texts(
            [(fixture / "dst.txt").read_text()], minimum=18, maximum=25
        )
        kickers = updater.parse_tier_texts(
            [(fixture / "kickers.txt").read_text()], minimum=18, maximum=25
        )
        self.assertEqual((len(overall), max(entry.tier for entry in overall)), (200, 26))
        self.assertEqual((len(dst), max(entry.tier for entry in dst)), (20, 6))
        self.assertEqual((len(kickers), max(entry.tier for entry in kickers)), (20, 5))

    def test_builds_complete_rankings_from_metadata(self):
        position_counts = {"QB": 27, "RB": 61, "WR": 74, "TE": 23, "DST": 11}
        names = [
            (f"{position} Player {number}", position)
            for position, count in position_counts.items()
            for number in range(1, count + 1)
        ]
        overall_names = names + [(f"Kicker {number}", "K") for number in range(1, 5)]
        overall = [
            updater.TierEntry(name, (rank - 1) // 8 + 1, rank)
            for rank, (name, _) in enumerate(overall_names, 1)
        ]
        ranking_rows = [{
            "RK": str(rank),
            "TIERS": "1",
            "PLAYER NAME": name,
            "TEAM": "TST",
            "POS": f"{position}1",
            "BYE WEEK": "7",
            "UPSIDE": "No rating",
            "BUST": "No rating",
            "SOS SEASON": "3 stars",
            "ECR VS. ADP": "+2",
        } for rank, (name, position) in enumerate(names, 1)]
        for number in range(12, 21):
            ranking_rows.append({
                **ranking_rows[-1],
                "RK": str(200 + number),
                "PLAYER NAME": f"DST Player {number}",
                "POS": "DST1",
            })
        kicker_rows = [{
            "name": f"Kicker {number}", "pos": "K", "tier": "1",
            "rank": str(180 + number), "adp": str(180 + number), "team": "TST",
            "bye": "7", "floor": "7", "ceiling": "10",
            "source_rank": str(number), "source_updated": "2026-08-17",
        } for number in range(1, 5)]
        dst = [
            updater.TierEntry(f"DST Player {number}", (number - 1) // 4 + 1, number)
            for number in range(1, 21)
        ]

        output = updater.build_rankings(overall, dst, ranking_rows, kicker_rows)
        self.assertEqual(len(output), 205)
        self.assertEqual(sum(row["POS"].startswith("DST") for row in output), 20)
        self.assertEqual(output[0]["ECR VS. ADP"], "+2")

    def test_builds_supported_kicker_pool(self):
        entries = [
            updater.TierEntry(f"Kicker {number}", (number - 1) // 5 + 1, number)
            for number in range(1, 17)
        ]
        existing = [{
            "name": entry.name, "pos": "K", "tier": "1", "rank": "180",
            "adp": "190", "team": "TST", "bye": "7", "floor": "7",
            "ceiling": "10", "source_rank": "1", "source_updated": "2026-08-01",
        } for entry in entries]
        output, unmatched = updater.build_kickers(entries, existing, date(2026, 8, 17))
        self.assertEqual(len(output), 16)
        self.assertEqual(output[-1]["source_rank"], "16")
        self.assertEqual(unmatched, [])


if __name__ == "__main__":
    unittest.main()
