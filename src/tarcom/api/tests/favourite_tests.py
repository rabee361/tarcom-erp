from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from tarcom.base.models import (
    CustomUser,
    FavouriteItem,
    Material,
    MaterialCategory,
    UnitOfMeasure,
)


class FavouriteAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            email="customer@example.com", password="StrongPass123!", is_verified=True
        )
        self.other_user = CustomUser.objects.create_user(
            email="other@example.com", password="StrongPass123!", is_verified=True
        )
        self.uom = UnitOfMeasure.objects.create(name="Piece", code="PCS")
        self.category = MaterialCategory.objects.create(name="Tools")
        self.material = Material.objects.create(
            name="Hammer",
            category=self.category,
            uom=self.uom,
            consumer_price=25.00,
            is_active=True,
        )
        self.other_material = Material.objects.create(
            name="Saw",
            category=self.category,
            uom=self.uom,
            consumer_price=40.00,
            is_active=True,
        )
        self.inactive_material = Material.objects.create(
            name="Retired", category=self.category, uom=self.uom, is_active=False
        )
        self.url = "/api/favourites/"

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.user)

    def test_list_favourites_authenticated(self):
        FavouriteItem.objects.create(user=self.user, material=self.material)
        FavouriteItem.objects.create(user=self.user, material=self.other_material)
        FavouriteItem.objects.create(user=self.other_user, material=self.material)

        self.authenticate()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 2)
        material_ids = {item["material"] for item in results}
        self.assertEqual(material_ids, {self.material.id, self.other_material.id})

    def test_list_favourites_unauthenticated(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_add_favourite_success(self):
        self.authenticate()
        response = self.client.post(
            self.url, {"material": self.material.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["material"], self.material.id)
        self.assertEqual(response.data["material_detail"]["name"], "Hammer")
        self.assertTrue(
            FavouriteItem.objects.filter(
                user=self.user, material=self.material
            ).exists()
        )

    def test_add_favourite_duplicate(self):
        FavouriteItem.objects.create(user=self.user, material=self.material)
        self.authenticate()
        response = self.client.post(
            self.url, {"material": self.material.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FavouriteItem.objects.filter(user=self.user).count(), 1)

    def test_add_favourite_inactive_material(self):
        self.authenticate()
        response = self.client.post(
            self.url, {"material": self.inactive_material.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(FavouriteItem.objects.filter(user=self.user).exists())

    def test_delete_favourite_by_id(self):
        favourite = FavouriteItem.objects.create(user=self.user, material=self.material)
        other_favourite = FavouriteItem.objects.create(
            user=self.other_user, material=self.material
        )
        self.authenticate()

        response = self.client.delete(f"{self.url}{favourite.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(FavouriteItem.objects.filter(id=favourite.id).exists())
        self.assertTrue(FavouriteItem.objects.filter(id=other_favourite.id).exists())

    def test_delete_favourite_by_material_id(self):
        FavouriteItem.objects.create(user=self.user, material=self.material)
        self.authenticate()

        response = self.client.delete(
            f"{self.url}remove-by-material/{self.material.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            FavouriteItem.objects.filter(
                user=self.user, material=self.material
            ).exists()
        )

        # Removing again reports a conflict.
        response = self.client.delete(
            f"{self.url}remove-by-material/{self.material.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_toggle_favourite(self):
        self.authenticate()

        response = self.client.post(
            f"{self.url}toggle/", {"material": self.material.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_favourite"])
        self.assertTrue(
            FavouriteItem.objects.filter(
                user=self.user, material=self.material
            ).exists()
        )

        response = self.client.post(
            f"{self.url}toggle/", {"material": self.material.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_favourite"])
        self.assertFalse(
            FavouriteItem.objects.filter(
                user=self.user, material=self.material
            ).exists()
        )

    def test_toggle_favourite_requires_material(self):
        self.authenticate()
        response = self.client.post(f"{self.url}toggle/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_check_favourite_status(self):
        self.authenticate()

        response = self.client.get(f"{self.url}check/", {"material": self.material.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_favourite"])

        FavouriteItem.objects.create(user=self.user, material=self.material)
        response = self.client.get(f"{self.url}check/", {"material": self.material.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_favourite"])

        response = self.client.get(f"{self.url}check/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
