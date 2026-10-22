import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management import call_command
from django.test import TestCase, override_settings

from tarcom.base.models import (
    Company,
    CustomUser,
    Material,
    MaterialCategory,
    # Order,
    Setting,
    UnitOfMeasure,
)

TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="tarcom_populate_test_media_")

COVER_DIR = (
    Path(settings.BASE_DIR)
    / "base"
    / "static"
    / "assets"
    / "images"
    / "categories"
    / "covers"
)


def tearDownModule():
    shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class PopulateProdDbTest(TestCase):
    def test_creates_only_the_system_categories_and_companies(self):
        call_command("populate_prod_db")

        categories = MaterialCategory.objects.all()
        self.assertEqual(categories.count(), 5)
        self.assertTrue(all(category.is_system for category in categories))

        laptops = MaterialCategory.objects.get(internal_name="laptops")
        self.assertEqual(laptops.name_en, "Laptops")
        self.assertEqual(laptops.name_ar, "لابتوبات")

        self.assertEqual(Company.objects.count(), 10)
        # rng is None in production, so an uploaded logo can only come from the
        # explicit "logo" entry in the JSON.
        self.assertTrue(Company.objects.get(name="Dell").has_uploaded_logo)
        self.assertFalse(Company.objects.get(name="Apple").has_uploaded_logo)

        self.assertEqual(Material.objects.count(), 0)
        self.assertEqual(CustomUser.objects.count(), 0)
        # self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(UnitOfMeasure.objects.count(), 0)

    def test_rerun_syncs_rows_back_to_the_json(self):
        call_command("populate_prod_db")
        laptops = MaterialCategory.objects.get(internal_name="laptops")

        MaterialCategory.objects.filter(pk=laptops.pk).update(
            name="Renamed", name_en="Renamed", name_ar="Renamed"
        )
        call_command("populate_prod_db")

        laptops.refresh_from_db()
        self.assertEqual(laptops.name_en, "Laptops")
        self.assertEqual(laptops.name_ar, "لابتوبات")
        self.assertTrue(laptops.is_system)
        self.assertEqual(MaterialCategory.objects.count(), 5)

    def test_rerun_adopts_a_category_created_before_internal_name_existed(self):
        category = MaterialCategory.objects.create(
            name="Laptops", name_en="Laptops", name_ar="قديم"
        )
        # Simulate a row that predates auto-generated internal names.
        MaterialCategory.objects.filter(pk=category.pk).update(internal_name=None)
        call_command("populate_prod_db")

        self.assertEqual(MaterialCategory.objects.count(), 5)
        laptops = MaterialCategory.objects.get(name_en="Laptops")
        self.assertEqual(laptops.internal_name, "laptops")
        self.assertTrue(laptops.is_system)

    def test_rerun_does_not_clobber_an_uploaded_cover_image(self):
        call_command("populate_prod_db")
        laptops = MaterialCategory.objects.get(internal_name="laptops")

        image_path = COVER_DIR / "batteries.jpg"
        with image_path.open("rb") as f:
            laptops.image.save("custom_cover.jpg", File(f), save=True)

        call_command("populate_prod_db")
        laptops.refresh_from_db()
        self.assertTrue(laptops.image.name.endswith("custom_cover.jpg"))

    def test_seeds_the_conversion_price_setting_once(self):
        call_command("populate_prod_db")
        call_command("populate_prod_db")

        settings = Setting.objects.filter(key_en="conversion_price")
        self.assertEqual(settings.count(), 1)
        self.assertEqual(settings.get().value, "140")
        self.assertEqual(settings.get().key_ar, "سعر الصرف")

    def test_rerun_does_not_clobber_an_edited_setting_value(self):
        call_command("populate_prod_db")
        Setting.objects.filter(key_en="conversion_price").update(value="200")

        call_command("populate_prod_db")

        self.assertEqual(
            Setting.objects.get(key_en="conversion_price").value, "200"
        )


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class PopulateDbTest(TestCase):
    def test_seeds_catalogue_from_the_json_files(self):
        call_command("populate_db")

        laptops = MaterialCategory.objects.get(internal_name="laptops")
        self.assertTrue(laptops.is_system)
        self.assertEqual(MaterialCategory.objects.count(), 5)
        self.assertEqual(Company.objects.count(), 10)
        self.assertEqual(Material.objects.count(), 10)
        self.assertEqual(CustomUser.objects.count(), 2)
        # self.assertEqual(Order.objects.count(), 6)

        dell_xps = Material.objects.get(name_en="Dell XPS 15")
        self.assertEqual(dell_xps.category_id, laptops.pk)
        self.assertEqual(dell_xps.company.name, "Dell")

    def test_dev_seeding_keeps_random_placeholder_logos(self):
        call_command("populate_db")
        self.assertTrue(
            all(company.has_uploaded_logo for company in Company.objects.all())
        )

    def test_populate_db_is_idempotent(self):
        call_command("populate_db")
        call_command("populate_db")
        self.assertEqual(MaterialCategory.objects.count(), 5)
        self.assertEqual(Company.objects.count(), 10)
        self.assertEqual(Material.objects.count(), 10)
        # self.assertEqual(Order.objects.count(), 6)

    def test_seeds_the_conversion_price_setting_once(self):
        call_command("populate_db")
        call_command("populate_db")

        settings = Setting.objects.filter(key_en="conversion_price")
        self.assertEqual(settings.count(), 1)
        self.assertEqual(settings.get().value, "140")
        self.assertEqual(settings.get().key_ar, "سعر الصرف")
