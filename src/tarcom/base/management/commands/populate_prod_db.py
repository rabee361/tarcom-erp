"""Seed the production database with the system categories, companies and settings.

Reads the same data/system_categories.json and data/system_companies.json
that the dev populate_db command uses, and creates ONLY those rows: no units
of measure, users, materials or orders. On top of that it seeds the system
settings (e.g. conversion_price=140) with their default values. Categories
are flagged is_system=True with their stable internal_name, so they cannot
be deleted from the dashboard or the API. The JSON files are the source of
truth -- re-running the command keeps the seeded rows in sync with them, but
images and logos that were already uploaded are never overwritten, and
settings that already exist (including user-edited values) are never
duplicated or overwritten. Company logos stay deterministic: only an
explicit "logo" entry is uploaded, otherwise the model default is kept (no
random placeholder logos in production).

Run:  python manage.py populate_prod_db    (idempotent, safe to re-run)
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify

from tarcom.base.models import Company, MaterialCategory, Setting

DATA_DIR = Path(__file__).resolve().parent / "data"

COVER_DIR = (
    Path(settings.BASE_DIR)
    / "base"
    / "static"
    / "assets"
    / "images"
    / "categories"
    / "covers"
)

LOGO_DIR = (
    Path(settings.BASE_DIR)
    / "base"
    / "static"
    / "assets"
    / "images"
    / "companies"
)


def load_system_data(filename):
    path = DATA_DIR / filename
    try:
        with path.open(encoding="utf-8") as f:
            entries = json.load(f)
    except FileNotFoundError:
        raise CommandError(f"Missing seed file: {path}") from None
    except json.JSONDecodeError as exc:
        raise CommandError(f"{filename} is not valid JSON: {exc}") from None
    if not isinstance(entries, list) or not entries:
        raise CommandError(f"{filename} must be a non-empty JSON list.")
    return entries


def _validate_entries(entries, filename, required):
    seen = {key: set() for key in required}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise CommandError(f"{filename} entry #{index} must be a JSON object.")
        missing = [key for key in required if not str(entry.get(key, "")).strip()]
        if missing:
            raise CommandError(
                f"{filename} entry #{index} is missing: {', '.join(missing)}"
            )
        for key in required:
            value = entry[key]
            if value in seen[key]:
                raise CommandError(f"{filename} has a duplicate {key}: {value!r}")
            seen[key].add(value)


def seed_system_categories():
    """Create or sync the system categories from data/system_categories.json.

    The internal_name is derived from name_en exactly the way the model's
    save() derives it (e.g. "Solar Boards" -> "solar_boards"), so rows are
    matched by that value, falling back to name_en so a category that already
    exists (e.g. seeded before internal_name was introduced) is adopted
    instead of colliding with the unique name constraint. The JSON is the
    source of truth: every run rewrites the display names and re-flags the
    row is_system=True. Returns the categories keyed by internal_name.
    """
    filename = "system_categories.json"
    entries = load_system_data(filename)
    _validate_entries(entries, filename, ["name_en", "name_ar"])

    categories = {}
    for entry in entries:
        internal_name = slugify(entry["name_en"]).replace("-", "_")
        category = MaterialCategory.objects.filter(
            Q(internal_name=internal_name) | Q(name_en=entry["name_en"])
        ).first()
        if category is None:
            category = MaterialCategory()
        category.name = entry["name_en"]
        category.name_en = entry["name_en"]
        category.name_ar = entry["name_ar"]
        category.is_system = True
        category.save()
        if not category.image and entry.get("image"):
            image_path = COVER_DIR / entry["image"]
            if image_path.exists():
                with image_path.open("rb") as f:
                    category.image.save(entry["image"], File(f), save=True)
        categories[internal_name] = category
    return categories


def seed_system_companies():
    """Create the companies from data/system_companies.json, keyed by name.

    Companies with an explicit "logo" in the JSON get that static brand logo
    uploaded; the rest keep the model default. Production stays deterministic
    -- no random placeholder logos. Already-uploaded logos are never
    overwritten.
    """
    filename = "system_companies.json"
    entries = load_system_data(filename)
    _validate_entries(entries, filename, ["name"])

    companies = {}
    for entry in entries:
        company, _ = Company.objects.get_or_create(name=entry["name"])
        if not company.has_uploaded_logo and entry.get("logo"):
            logo_path = LOGO_DIR / entry["logo"]
            if logo_path.exists():
                with logo_path.open("rb") as f:
                    company.logo.save(entry["logo"], File(f), save=True)
        companies[entry["name"]] = company
    return companies


def seed_system_settings():
    setting, _ = Setting.objects.get_or_create(
        key_en="conversion_price",
        defaults={
            "key_en": "conversion_price",
            "key_ar": "سعر الصرف",
            "value": "140",
        },
    )
    if not setting.key_ar:
        setting.key_ar = "سعر الصرف"
        setting.save(update_fields=["key_ar"])
    return 1


class Command(BaseCommand):
    help = (
        "Populate the database with the system categories, companies and "
        "settings only (for production; no users, materials or orders)."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        categories = seed_system_categories()
        companies = seed_system_companies()
        settings_count = seed_system_settings()
        self.stdout.write(
            self.style.SUCCESS(
                f"Populated: {len(categories)} categories, "
                f"{len(companies)} companies, {settings_count} settings."
            )
        )
