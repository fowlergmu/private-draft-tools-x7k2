import sys
import unittest
from datetime import date
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_nfl_daily_news as updater


def feed_item(text, created, rkey="abc"):
    return {
        "post": {
            "uri": f"at://did:example/app.bsky.feed.post/{rkey}",
            "author": {"handle": updater.HANDLE},
            "record": {"text": text, "createdAt": created},
        }
    }


class InjuryUpdaterTests(unittest.TestCase):
    def setUp(self):
        self.players = [
            updater.Player("Zay Flowers", "WR", 1),
            updater.Player("Luther Burden III", "WR", 2),
            updater.Player("Jaylin Noel", "WR", 3),
        ]

    def test_matches_suffix_alias_and_classifies_monitor(self):
        rows = updater.build_snapshot(
            [feed_item("Luther Burden limped off with a trainer.", "2026-08-08T14:00:00Z")],
            self.players,
            {},
            date(2026, 8, 9),
            7,
        )
        self.assertEqual(rows[0]["name"], "Luther Burden III")
        self.assertEqual(rows[0]["status"], "Monitor")
        self.assertEqual(rows[0]["injury"], "Undisclosed")

    def test_newest_post_wins(self):
        rows = updater.build_snapshot(
            [
                feed_item("Zay Flowers limped off with trainers.", "2026-08-08T16:00:00Z", "one"),
                feed_item("Zay Flowers considered day-to-day with quad contusion.", "2026-08-08T17:00:00Z", "two"),
            ],
            self.players,
            {},
            date(2026, 8, 9),
            7,
        )
        self.assertEqual(rows[0]["status"], "Day-to-day")
        self.assertEqual(rows[0]["injury"], "Quad contusion")
        self.assertTrue(rows[0]["source"].endswith("/two"))

    def test_active_update_removes_existing_player(self):
        existing = {
            "Jaylin Noel": {
                "name": "Jaylin Noel",
                "pos": "WR",
                "status": "NFI",
                "injury": "Undisclosed",
                "updated": "2026-08-07",
                "source": "https://example.com/old",
                "notes": "Placed on NFI",
            }
        }
        rows = updater.build_snapshot(
            [feed_item("Jaylin Noel activated from NFI list.", "2026-08-08T12:00:00Z")],
            self.players,
            existing,
            date(2026, 8, 9),
            7,
        )
        self.assertEqual(rows, [])

    def test_recent_existing_status_is_preserved(self):
        existing = {
            "Zay Flowers": {
                "name": "Zay Flowers",
                "pos": "WR",
                "status": "Questionable",
                "injury": "Quadriceps",
                "updated": "2026-08-05",
                "source": "https://example.com/old",
                "notes": "Missed practice",
            }
        }
        rows = updater.build_snapshot([], self.players, existing, date(2026, 8, 9), 7)
        self.assertEqual(rows[0]["name"], "Zay Flowers")

    def test_stale_short_term_status_expires(self):
        existing = {
            "Zay Flowers": {
                "name": "Zay Flowers",
                "pos": "WR",
                "status": "Monitor",
                "injury": "Quadriceps",
                "updated": "2026-07-01",
                "source": "https://example.com/old",
                "notes": "Old update",
            }
        }
        rows = updater.build_snapshot([], self.players, existing, date(2026, 8, 9), 7)
        self.assertEqual(rows, [])

    def test_ordinary_use_of_back_is_not_an_injury(self):
        rows = updater.build_snapshot(
            [feed_item("Zay Flowers wants to get the position back where it belongs.", "2026-08-08T12:00:00Z")],
            self.players,
            {},
            date(2026, 8, 9),
            7,
        )
        self.assertEqual(rows, [])

    def test_player_reporting_another_injury_is_not_tagged(self):
        rows = updater.build_snapshot(
            [feed_item("Zay Flowers said CB Example Player (knee) should be fine after an injury.", "2026-08-08T12:00:00Z")],
            self.players,
            {},
            date(2026, 8, 9),
            7,
        )
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
