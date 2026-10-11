"""Pin the default pagination contract (page size 10, capped page_size, next links).

The default was recently switched to CustomNumberPagination (10 rows per page);
these tests create enough rows to cross page boundaries so that change cannot
silently drift.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from tarcom.base.models import UnitOfMeasure

TOTAL = 55


class DefaultPaginationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        for i in range(1, TOTAL + 1):
            UnitOfMeasure.objects.create(name=f"Unit {i:02d}", code=f"U{i:02d}")
        self.url = "/api/units/"

    def test_default_page_size_is_10(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], TOTAL)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIsNotNone(response.data["next"])
        self.assertIsNone(response.data["previous"])

    def test_following_next_links_walks_all_pages_without_overlap(self):
        page_ids = []
        pages = 0
        url = self.url
        while url:
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            page_ids.extend(item["id"] for item in response.data["results"])
            pages += 1
            url = response.data["next"]

        self.assertEqual(pages, 6)
        self.assertEqual(len(page_ids), TOTAL)
        self.assertEqual(len(set(page_ids)), TOTAL)

    def test_final_page_holds_the_remainder_and_has_no_next(self):
        response = self.client.get(f"{self.url}?page=6")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), TOTAL % 10)
        self.assertIsNone(response.data["next"])
        self.assertIsNotNone(response.data["previous"])

    def test_page_size_query_param_overrides_default(self):
        response = self.client.get(f"{self.url}?page_size=15")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], TOTAL)
        self.assertEqual(len(response.data["results"]), 15)

    def test_page_size_is_capped_at_max_page_size(self):
        response = self.client.get(f"{self.url}?page_size=100")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 50)

    def test_page_beyond_last_returns_404(self):
        response = self.client.get(f"{self.url}?page=999")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], status.HTTP_404_NOT_FOUND)
