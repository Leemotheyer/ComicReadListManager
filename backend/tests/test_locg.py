import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.locg import (
    ACTIVITY_ID_PATTERNS,
    _extract_activity_id,
    _is_collected_edition_page,
    _parse_collected_edition_page,
    _parse_issue_rows,
    _single_issue_from_page,
    fetch_collected_edition,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
COMIC_DETAIL_HTML = (FIXTURES / "comic_detail.html").read_text(encoding="utf-8")


class LocgActivityIdTest(unittest.TestCase):
    def test_extract_activity_id_supports_multiple_patterns(self) -> None:
        self.assertEqual(_extract_activity_id("DashboardFeed.loadThread(12345)"), 12345)
        self.assertEqual(_extract_activity_id("feed.loadThread(67890)"), 67890)
        self.assertEqual(
            _extract_activity_id('<div data-thread-id="55555"></div>'),
            55555,
        )

    def test_all_activity_patterns_are_compiled(self) -> None:
        self.assertGreaterEqual(len(ACTIVITY_ID_PATTERNS), 3)


class LocgCollectedEditionParsingTest(unittest.TestCase):
    def test_parses_story_breakdown_with_linked_issues(self) -> None:
        html = """
        <section class="header-intro"><a href="/comics/dc">DC Comics</a></section>
        <section id="stories">
          <details class="story-item is-expandable">
            <summary>
              <h4 class="story-title">The Man Without Fear</h4>
              <div class="copy-really-small">
                Story · <a href="/comic/100001/daredevil-168">Daredevil #168</a> · Mar 1981
              </div>
            </summary>
          </details>
          <details class="story-item story-item-overview">
            <summary><h4 class="story-title">Overview</h4></summary>
          </details>
        </section>
        """
        items = _parse_collected_edition_page(html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].series, "Daredevil")
        self.assertEqual(items[0].issue_number, "168")
        self.assertEqual(items[0].locg_id, 100001)

    def test_parses_real_comic_detail_fixture_story_link(self) -> None:
        items = _parse_collected_edition_page(COMIC_DETAIL_HTML)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].series, "Batman / Wonder Woman: Truth")
        self.assertEqual(items[0].issue_number, "1")
        self.assertEqual(items[0].locg_id, 8844555)


class LocgSingleIssueParsingTest(unittest.TestCase):
    def test_detects_single_issue_page(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(COMIC_DETAIL_HTML, "lxml")
        self.assertFalse(_is_collected_edition_page(soup))

    def test_detects_collected_edition_page(self) -> None:
        from bs4 import BeautifulSoup

        html = """
        <h1>Invincible Vol. 1 TP</h1>
        <section id="summary"><div class="copy-small">Trade Paperback · 200 pages</div></section>
        """
        soup = BeautifulSoup(html, "lxml")
        self.assertTrue(_is_collected_edition_page(soup))

    def test_builds_single_issue_from_page_header(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(COMIC_DETAIL_HTML, "lxml")
        issue = _single_issue_from_page(
            soup,
            locg_comic_id=9559460,
            default_publisher="DC Comics",
        )
        self.assertEqual(issue.series, "Batman")
        self.assertEqual(issue.issue_number, "8")
        self.assertEqual(issue.locg_id, 9559460)
        self.assertEqual(issue.store_date, "Jun 2026")


class LocgCommunityListParsingTest(unittest.TestCase):
    def test_parses_standard_issue_rows(self) -> None:
        html = """
        <ul>
          <li class="issue" data-comic="9430629" data-row="1">
            <div class="title">Batman #105</div>
            <div class="publisher">DC Comics</div>
            <div class="date">Mar 2022</div>
          </li>
        </ul>
        """
        items = _parse_issue_rows(html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].series, "Batman")
        self.assertEqual(items[0].issue_number, "105")

    def test_parses_data_sorting_fallback_rows(self) -> None:
        html = """
        <div data-sorting="Detective Comics #1058"></div>
        <div data-sorting="Batman #105"></div>
        """
        items = _parse_issue_rows(html, default_publisher="DC Comics")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].series, "Detective Comics")
        self.assertEqual(items[1].series, "Batman")


class LocgFetchComicPageTest(unittest.TestCase):
    def test_fetch_comic_page_imports_single_issue_when_no_story_breakdown(self) -> None:
        with patch("app.services.locg._get_page") as get_page:
            response = unittest.mock.MagicMock()
            response.status_code = 200
            response.text = COMIC_DETAIL_HTML
            get_page.return_value = response

            source = fetch_collected_edition(
                "https://leagueofcomicgeeks.com/comic/9559460/batman-8"
            )

        self.assertEqual(source.source_type, "single_issue")
        self.assertEqual(len(source.items), 1)
        self.assertEqual(source.items[0].series, "Batman")
        self.assertEqual(source.items[0].issue_number, "8")


if __name__ == "__main__":
    unittest.main()
