import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.services.komga import (
    KomgaClient,
    _dedupe_book_ids,
    _names_match,
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
