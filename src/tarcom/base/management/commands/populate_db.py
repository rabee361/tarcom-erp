"""Seed the database with deterministic fake data for local development.

The storefront categories and companies come from data/system_categories.json
and data/system_companies.json (shared with populate_prod_db); categories
seeded from there are flagged is_system=True with their stable internal_name.
On top of that this seeds the system settings (e.g. conversion_price=140)
with their default values, the units of measure the materials reference, 10
materials linked to those categories/companies with every spec key/value pair
filled, 2 active users (one customer, one supplier -- every non-admin type),
and 3 orders per user with 1-2 line items each. No OTP codes are generated;
the users are marked verified and active so they can log in immediately.

Run:  python manage.py populate_db            (idempotent, safe to re-run)
      python manage.py populate_db --flush    (wipe seeded rows first)
      python manage.py populate_db --seed 7   (different but reproducible data)
"""

import json
import random
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify

from tarcom.base.models import (
    Company,
    CustomUser,
    Material,
    MaterialCategory,
    # Order,
    # OrderItem,
    Setting,
    UnitOfMeasure,
)
from tarcom.utils.enums import (
    # OrderStatus,
    PaymentMethod,
    PaymentStatus,
    UserType,
)

PASSWORD = "Passw0rd!123"

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

# Only these 4 brand logos exist so far; they are assigned randomly to
# companies without an explicit JSON logo until the real logos are added.
LOGO_FILES = ["DELL.png", "acer.png", "asus.png", "lenovo.png"]

UNITS = [
    ("EA", "Each", "حبة"),
    ("BX", "Box", "صندوق"),
]

MATERIALS = [
    {
        "name_en": "Dell XPS 15",
        "name_ar": "لابتوب ديل XPS 15",
        "company": "Dell",
        "desc_en": "15.6-inch OLED creator laptop with 13th-gen Intel Core i7.",
        "desc_ar": "لابتوب بشاشة OLED مقاس 15.6 بوصة للمبدعين بمعالج إنتل كور i7 من الجيل الثالث عشر.",
        "category": "laptops",
        "uom": "EA",
        "supplier_price": "900.00",
        "consumer_price": "1200.00",
        "specs": [
            ("Brand", "Dell"),
            ("CPU", "Intel Core i7-13700H"),
            ("RAM", "16GB DDR5"),
            ("Storage", "512GB NVMe SSD"),
            ("Display", '15.6" OLED 3.5K'),
        ],
    },
    {
        "name_en": "MacBook Air M3",
        "name_ar": "ماك بوك إير M3",
        "company": "Apple",
        "desc_en": "Thin and light 13.6-inch laptop powered by the Apple M3 chip.",
        "desc_ar": "لابتوب نحيف وخفيف بشاشة 13.6 بوصة يعمل بشريحة أبل M3.",
        "category": "laptops",
        "uom": "EA",
        "supplier_price": "850.00",
        "consumer_price": "1100.00",
        "specs": [
            ("Brand", "Apple"),
            ("CPU", "Apple M3 8-core"),
            ("RAM", "8GB Unified Memory"),
            ("Storage", "256GB SSD"),
            ("Display", '13.6" Liquid Retina'),
        ],
    },
    {
        "name_en": "Li-ion 18650 Cell",
        "name_ar": "خلية ليثيوم أيون 18650",
        "company": "LG Chem",
        "desc_en": "High-drain rechargeable 18650 lithium-ion cell, sold in boxes.",
        "desc_ar": "خلية ليثيوم أيون قابلة لإعادة الشحن عالية التصريف 18650، تُباع بالصندوق.",
        "category": "batteries",
        "uom": "BX",
        "supplier_price": "2.00",
        "consumer_price": "4.00",
        "specs": [
            ("Chemistry", "Li-ion"),
            ("Capacity", "3000mAh"),
            ("Voltage", "3.7V"),
            ("Rechargeable", "Yes"),
            ("Cycle Life", "500 cycles"),
        ],
    },
    {
        "name_en": "12V Deep Cycle Battery",
        "name_ar": "بطارية 12 فولت عميقة التفريغ",
        "company": "Exide",
        "desc_en": "AGM lead-acid deep-cycle battery for solar and backup systems.",
        "desc_ar": "بطارية حمضية AGM عميقة التفريغ لأنظمة الطاقة الشمسية والأنظمة الاحتياطية.",
        "category": "batteries",
        "uom": "EA",
        "supplier_price": "120.00",
        "consumer_price": "180.00",
        "specs": [
            ("Type", "Lead-Acid AGM"),
            ("Voltage", "12V"),
            ("Capacity", "100Ah"),
            ("Terminals", "M8 Bolt"),
            ("Cycle Life", "500 cycles"),
        ],
    },
    {
        "name_en": "Mono Solar Panel 200W",
        "name_ar": "لوح شمسي مونو 200 واط",
        "company": "Canadian Solar",
        "desc_en": "200-watt monocrystalline solar panel with high cell efficiency.",
        "desc_ar": "لوح طاقة شمسية أحادي التبلور بقدرة 200 واط بكفاءة خلايا عالية.",
        "category": "solar_boards",
        "uom": "EA",
        "supplier_price": "90.00",
        "consumer_price": "140.00",
        "specs": [
            ("Type", "Monocrystalline"),
            ("Power", "200W"),
            ("Voltage", "18V"),
            ("Efficiency", "21%"),
            ("Cells", "60 cells"),
        ],
    },
    {
        "name_en": "MPPT Charge Controller 30A",
        "name_ar": "منظم شحن MPPT 30 أمبير",
        "company": "Victron Energy",
        "desc_en": "30-amp MPPT solar charge controller with auto system voltage.",
        "desc_ar": "منظم شحن شمسي بتقنية MPPT بتيار 30 أمبير مع جهد نظام تلقائي.",
        "category": "solar_boards",
        "uom": "EA",
        "supplier_price": "35.00",
        "consumer_price": "60.00",
        "specs": [
            ("Type", "MPPT"),
            ("Current", "30A"),
            ("System Voltage", "12V/24V Auto"),
            ("Max PV Input", "100V"),
            ("Protection", "IP68"),
        ],
    },
    {
        "name_en": "USB-C to USB-C Cable 1m",
        "name_ar": "كابل USB-C إلى USB-C بطول 1 متر",
        "company": "Anker",
        "desc_en": "Braided 100W power-delivery USB-C cable with USB 3.2 data.",
        "desc_ar": "كابل USB-C مضفر باستطاعة 100 واط للشحن السريع مع نقل بيانات USB 3.2.",
        "category": "cables",
        "uom": "EA",
        "supplier_price": "1.50",
        "consumer_price": "4.00",
        "specs": [
            ("Connector", "USB-C"),
            ("Length", "1m"),
            ("Power", "100W PD"),
            ("Data", "USB 3.2 Gen 2"),
            ("Shielding", "Braided"),
        ],
    },
    {
        "name_en": "HDMI 2.1 Cable 2m",
        "name_ar": "كابل HDMI 2.1 بطول 2 متر",
        "company": "Ugreen",
        "desc_en": "Ultra-high-speed HDMI 2.1 cable supporting 8K at 60Hz.",
        "desc_ar": "كابل HDMI 2.1 فائق السرعة يدعم دقة 8K بمعدل 60 هرتز.",
        "category": "cables",
        "uom": "EA",
        "supplier_price": "3.00",
        "consumer_price": "7.00",
        "specs": [
            ("Connector", "HDMI Type-A"),
            ("Length", "2m"),
            ("Version", "HDMI 2.1"),
            ("Bandwidth", "48Gbps"),
            ("Max Resolution", "8K@60Hz"),
        ],
    },
    {
        "name_en": "Smart Inverter AC 1.5 Ton",
        "name_ar": "مكيف سمارت انفرتر 1.5 طن",
        "company": "LG",
        "desc_en": "Wi-Fi enabled split inverter air conditioner, 18000 BTU.",
        "desc_ar": "مكيف هواء سبليت انفرتر يدعم الواي فاي، 18000 وحدة حرارية.",
        "category": "home_tech",
        "uom": "EA",
        "supplier_price": "400.00",
        "consumer_price": "600.00",
        "specs": [
            ("Type", "Split Inverter"),
            ("Capacity", "1.5 Ton"),
            ("Cooling", "18000 BTU"),
            ("Power Rating", "1.5kW"),
            ("Smart Features", "Wi-Fi + App Control"),
        ],
    },
    {
        "name_en": "Smart French-Door Fridge 500L",
        "name_ar": "ثلاجة سمارت فرنش دور 500 لتر",
        "company": "Samsung",
        "desc_en": "500-litre frost-free smart refrigerator with touch display.",
        "desc_ar": "ثلاجة ذكية بسعة 500 لتر بدون ثلج مع شاشة تعمل باللمس.",
        "category": "home_tech",
        "uom": "EA",
        "supplier_price": "700.00",
        "consumer_price": "1000.00",
        "specs": [
            ("Type", "French Door"),
            ("Capacity", "500L"),
            ("Cooling", "No Frost"),
            ("Energy Rating", "A++"),
            ("Smart Features", "Touch Display + Wi-Fi"),
        ],
    },
]

USERS = [
    ("customer@tarcom.test", "Nour", "Haddad", UserType.CUSTOMER, "+963991000001"),
    ("supplier@tarcom.test", "Sami", "Khouri", UserType.SUPPLIER, "+963992000002"),
]

ADDRESSES = [
    "12 Al-Jazeera St, Damascus",
    "45 Nile Corniche, Aleppo",
    "7 Garden Square, Homs",
]


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


def seed_system_companies(rng):
    """Create the companies from data/system_companies.json, keyed by name.

    Companies with an explicit "logo" in the JSON get that static brand logo
    uploaded; the rest get one of the placeholder logos at random until the
    real logos are added. Already-uploaded logos are never overwritten.
    """
    filename = "system_companies.json"
    entries = load_system_data(filename)
    _validate_entries(entries, filename, ["name"])

    companies = {}
    for entry in entries:
        company, _ = Company.objects.get_or_create(name=entry["name"])
        if not company.has_uploaded_logo:
            logo_filename = entry.get("logo") or rng.choice(LOGO_FILES)
            logo_path = LOGO_DIR / logo_filename
            if logo_path.exists():
                with logo_path.open("rb") as f:
                    company.logo.save(logo_filename, File(f), save=True)
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
    help = "Populate the database with fake categories, materials, users and orders."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing orders, materials, categories, units and the seeded users first.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="RNG seed for reproducible random choices (default: 42).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(options["seed"])

        if options["flush"]:
            self._flush()

        uoms = self._seed_uoms()
        categories = seed_system_categories()
        companies = self._seed_companies(rng)
        materials = self._seed_materials(uoms, categories, companies)
        users = self._seed_users()
        settings_count = seed_system_settings()

        self.stdout.write(
            self.style.SUCCESS(
                f"Populated: {len(uoms)} units, {len(categories)} categories, "
                f"{len(companies)} companies, {len(materials)} materials, "
                f"{settings_count} settings."
            )
        )

    def _flush(self):
        Material.objects.all().delete()
        MaterialCategory.objects.all().delete()
        UnitOfMeasure.objects.all().delete()
        Company.objects.all().delete()
        CustomUser.objects.filter(email__in=[u[0] for u in USERS]).delete()
        self.stdout.write("Flushed existing seeded data.")

    def _seed_uoms(self):
        uoms = {}
        for code, name_en, name_ar in UNITS:
            uom, _ = UnitOfMeasure.objects.get_or_create(
                code=code,
                defaults={"name": name_en, "name_en": name_en, "name_ar": name_ar},
            )
            uoms[code] = uom
        return uoms

    def _seed_companies(self, rng):
        """Seed the companies from system_companies.json, then make sure every
        company the fake materials reference is actually in that file."""
        companies = seed_system_companies(rng)
        missing = sorted({spec["company"] for spec in MATERIALS} - companies.keys())
        if missing:
            raise CommandError(
                "system_companies.json is missing companies referenced by "
                f"the seed materials: {', '.join(missing)}"
            )
        return companies

    def _seed_materials(self, uoms, categories, companies):
        materials = []
        for spec in MATERIALS:
            defaults = {
                "name": spec["name_en"],
                "name_ar": spec["name_ar"],
                "description": spec["desc_en"],
                "description_en": spec["desc_en"],
                "description_ar": spec["desc_ar"],
                "category": categories[spec["category"]],
                "uom": uoms[spec["uom"]],
                "company": companies[spec["company"]],
                "supplier_price": Decimal(spec["supplier_price"]),
                "consumer_price": Decimal(spec["consumer_price"]),
                "is_active": True,
            }
            for index, (key, value) in enumerate(spec["specs"], start=1):
                defaults[f"spec_key{index}"] = key
                defaults[f"spec_val{index}"] = value

            material, _ = Material.objects.update_or_create(
                name_en=spec["name_en"], defaults=defaults
            )
            materials.append(material)
        return materials

    def _seed_users(self):
        users = []
        for email, first_name, last_name, user_type, phone in USERS:
            user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "user_type": user_type,
                    "phone": phone,
                    "is_active": True,
                    "is_verified": True,
                },
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            users.append(user)
        return users
