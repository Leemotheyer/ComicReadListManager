import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.services.komga import (
    KomgaClient,
    _dedupe_book_ids,
    _names_match,
    _pick_best_book_id,
    _series_year_from_komga,
    _year_from_series_title,
    format_komga_error,
)


class KomgaPushHelpersTest(unittest.TestCase):
    def test_names_match_is_case_insensitive(self) -> None:
        self.assertTrue(_names_match("Batman", "batman"))
        self.assertFalse(_names_match("Batman", "Superman"))

    def test_dedupe_book_ids_preserves_order(self) -> None:
        self.assertEqual(
            _dedupe_book_ids(["a", "b", "a", "c", "b"]),
            ["a", "b", "c"],
        )

    def test_resolve_items_manual_override_replaces_auto_match(self) -> None:
        preview_items = [
            {
                "list_item_id": 1,
                "komga_book_id": "auto-book",
                "status": "matched",
                "message": "Auto match",
            }
        ]
        book_ids, resolved = KomgaClient.resolve_items(
            preview_items,
            manual_mappings={1: "manual-book"},
            manual_labels={1: "Picked manually"},
        )
        self.assertEqual(book_ids, ["manual-book"])
        self.assertEqual(resolved[0]["status"], "manual")
        self.assertEqual(resolved[0]["komga_book_id"], "manual-book")

    def test_resolve_items_excluded_rejects_auto_match(self) -> None:
        preview_items = [
            {
                "list_item_id": 1,
                "komga_book_id": "auto-book",
                "status": "matched",
            }
        ]
        book_ids, resolved = KomgaClient.resolve_items(
            preview_items,
            excluded_ids={1},
        )
        self.assertEqual(book_ids, [])
        self.assertEqual(resolved[0]["status"], "unmatched")
        self.assertIsNone(resolved[0]["komga_book_id"])

    def test_year_from_series_title(self) -> None:
        self.assertEqual(_year_from_series_title("Hawkeye (2012)"), 2012)
        self.assertIsNone(_year_from_series_title("Hawkeye"))

    def test_series_year_from_komga_prefers_release_date(self) -> None:
        year = _series_year_from_komga(
            {"releaseDate": "2017-03-15", "title": "Hawkeye (2012)"}
        )
        self.assertEqual(year, 2017)

    def test_pick_best_book_id_matches_volume_year(self) -> None:
        match_entry = {
            "request": {"series": ["Hawkeye", "Hawkeye (2012)"], "number": "1"},
            "matches": [
                {
                    "series": {
                        "seriesId": "series-2012",
                        "title": "Hawkeye",
                        "releaseDate": "2012-08-01",
                    },
                    "books": [
                        {"bookId": "book-2012", "number": "1", "title": "Hawkeye #1"}
                    ],
                },
                {
                    "series": {
                        "seriesId": "series-2017",
                        "title": "Hawkeye",
                        "releaseDate": "2017-03-01",
                    },
                    "books": [
                        {"bookId": "book-2017", "number": "1", "title": "Hawkeye #1"}
                    ],
                },
            ],
        }
        book_id = _pick_best_book_id(
            match_entry,
            issue_number="1",
            volume_year=2012,
            cover_year=None,
        )
        self.assertEqual(book_id, "book-2012")

    def test_pick_best_book_id_rejects_wrong_issue_number(self) -> None:
        match_entry = {
            "request": {"series": ["Hawkeye"], "number": "2"},
            "matches": [
                {
                    "series": {
                        "seriesId": "series-2012",
                        "title": "Hawkeye",
                        "releaseDate": "2012-08-01",
                    },
                    "books": [
                        {"bookId": "book-2012", "number": "1", "title": "Hawkeye #1"}
                    ],
                }
            ],
        }
        book_id = _pick_best_book_id(
            match_entry,
            issue_number="2",
            volume_year=2012,
            cover_year=None,
        )
        self.assertIsNone(book_id)

    def test_pick_best_book_id_ambiguous_without_volume_year(self) -> None:
        match_entry = {
            "request": {"series": ["Hawkeye"], "number": "1"},
            "matches": [
                {
                    "series": {
                        "seriesId": "series-2012",
                        "title": "Hawkeye",
                        "releaseDate": "2012-08-01",
                    },
                    "books": [
                        {"bookId": "book-2012", "number": "1", "title": "Hawkeye #1"}
                    ],
                },
                {
                    "series": {
                        "seriesId": "series-2017",
                        "title": "Hawkeye",
                        "releaseDate": "2017-03-01",
                    },
                    "books": [
                        {"bookId": "book-2017", "number": "1", "title": "Hawkeye #1"}
                    ],
                },
            ],
        }
        book_id = _pick_best_book_id(
            match_entry,
            issue_number="1",
            volume_year=None,
            cover_year=None,
        )
        self.assertIsNone(book_id)

    def test_classify_list_uses_volume_year_for_same_titled_series(self) -> None:
        client = KomgaClient()
        read_list = unittest.mock.MagicMock()
        read_list.name = "Test"
        item = unittest.mock.MagicMock()
        item.id = 1
        item.cv_volume_id = 10
        item.series = "Hawkeye"
        item.issue_number = "1"
        item.volume_year = 2017
        item.cover_year = None
        item.sort_order = 0
        read_list.items = [item]

        match_response = {
            "readListMatch": {"name": "Test"},
            "requests": [
                {
                    "request": {"series": ["Hawkeye", "Hawkeye (2017)"], "number": "1"},
                    "matches": [
                        {
                            "series": {
                                "seriesId": "series-2012",
                                "title": "Hawkeye",
                                "releaseDate": "2012-08-01",
                            },
                            "books": [
                                {
                                    "bookId": "book-2012",
                                    "number": "1",
                                    "title": "Hawkeye #1",
                                }
                            ],
                        },
                        {
                            "series": {
                                "seriesId": "series-2017",
                                "title": "Hawkeye",
                                "releaseDate": "2017-03-01",
                            },
                            "books": [
                                {
                                    "bookId": "book-2017",
                                    "number": "1",
                                    "title": "Hawkeye #1",
                                }
                            ],
                        },
                    ],
                }
            ],
        }

        result = client.classify_list(read_list, match_response)
        self.assertEqual(result["items"][0]["komga_book_id"], "book-2017")
        self.assertEqual(result["matched_count"], 1)

    def test_classify_list_avoids_duplicate_komga_books(self) -> None:
        client = KomgaClient()
        read_list = unittest.mock.MagicMock()
        read_list.name = "Test"

        def make_item(item_id: int, issue_number: str) -> unittest.mock.MagicMock:
            item = unittest.mock.MagicMock()
            item.id = item_id
            item.cv_volume_id = 10
            item.series = "Hawkeye"
            item.issue_number = issue_number
            item.volume_year = 2012
            item.cover_year = None
            item.sort_order = item_id
            return item

        read_list.items = [make_item(1, "1"), make_item(2, "1")]

        match_entry = {
            "request": {"series": ["Hawkeye", "Hawkeye (2012)"], "number": "1"},
            "matches": [
                {
                    "series": {
                        "seriesId": "series-2012",
                        "title": "Hawkeye",
                        "releaseDate": "2012-08-01",
                    },
                    "books": [
                        {"bookId": "book-2012", "number": "1", "title": "Hawkeye #1"}
                    ],
                }
            ],
        }
        match_response = {
            "readListMatch": {"name": "Test"},
            "requests": [match_entry, match_entry],
        }

        result = client.classify_list(read_list, match_response)
        matched_ids = [
            item["komga_book_id"]
            for item in result["items"]
            if item.get("komga_book_id")
        ]
        self.assertEqual(matched_ids, ["book-2012"])
        self.assertIsNone(result["items"][1]["komga_book_id"])
        self.assertEqual(result["items"][1]["status"], "unmatched")
        self.assertIn("already matched", result["items"][1]["message"])

    def test_format_komga_error_includes_response_message(self) -> None:
        request = httpx.Request("POST", "http://komga/api/v1/readlists")
        response = httpx.Response(
            400,
            request=request,
            json={"message": "A read list with that name already exists"},
        )
        exc = httpx.HTTPStatusError("bad request", request=request, response=response)
        self.assertIn(
            "A read list with that name already exists",
            format_komga_error(exc),
        )


class KomgaClientPushTest(unittest.IsolatedAsyncioTestCase):
    async def test_push_dedupes_duplicate_book_ids_before_create(self) -> None:
        client = KomgaClient()
        preview = {
            "list_name": "Test List",
            "existing_komga_read_list_id": None,
            "items": [
                {
                    "list_item_id": 1,
                    "komga_book_id": "book-1",
                    "status": "matched",
                },
                {
                    "list_item_id": 2,
                    "komga_book_id": "book-1",
                    "status": "matched",
                },
                {
                    "list_item_id": 3,
                    "komga_book_id": "book-2",
                    "status": "matched",
                },
            ],
        }

        with (
            patch.object(client, "preview", AsyncMock(return_value=preview)),
            patch.object(client, "create_read_list", AsyncMock(return_value={"id": "rl-1"})) as create,
        ):
            read_list = unittest.mock.MagicMock()
            read_list.description = None
            read_list.tags = []
            read_list.items = []

            result = await client.push(read_list)

        create.assert_awaited_once()
        self.assertEqual(create.await_args.args[2], ["book-1", "book-2"])
        self.assertEqual(result["books_pushed"], 2)
        self.assertEqual(result["books_skipped"], 1)

    async def test_create_falls_back_to_update_when_name_exists(self) -> None:
        client = KomgaClient()
        preview = {
            "list_name": "Existing List",
            "existing_komga_read_list_id": None,
            "items": [
                {
                    "list_item_id": 1,
                    "komga_book_id": "book-1",
                    "status": "matched",
                },
            ],
        }
        request = httpx.Request("POST", "http://komga/api/v1/readlists")
        response = httpx.Response(
            400,
            request=request,
            text="A read list with that name already exists",
        )
        create_error = httpx.HTTPStatusError("bad request", request=request, response=response)

        with (
            patch.object(client, "preview", AsyncMock(return_value=preview)),
            patch.object(client, "create_read_list", AsyncMock(side_effect=create_error)),
            patch.object(
                client,
                "find_read_list_by_name",
                AsyncMock(return_value={"id": "rl-existing", "name": "existing list"}),
            ),
            patch.object(client, "update_read_list", AsyncMock()) as update,
        ):
            read_list = unittest.mock.MagicMock()
            read_list.description = None
            read_list.tags = []
            read_list.items = []

            result = await client.push(read_list)

        update.assert_awaited_once_with(
            "rl-existing",
            name="Existing List",
            summary="",
            book_ids=["book-1"],
            ordered=True,
        )
        self.assertEqual(result["action"], "updated")
        self.assertEqual(result["komga_read_list_id"], "rl-existing")


if __name__ == "__main__":
    unittest.main()
