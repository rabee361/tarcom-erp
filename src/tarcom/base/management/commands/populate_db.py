"""Seed the database with deterministic fake data for local development.

Tarcom is an electronics marketplace, so this seeds the 5 real storefront
categories (Laptops, Batteries, Solar Boards, Cables, Home Tech) -- each
seeded with its icon uploaded into media storage -- plus the
units of measure they reference, 10 materials with every spec key/value pair
filled, 2 active users (one customer, one supplier -- every non-admin type),
and 3 orders per user with 1-2 line items each. No OTP codes are generated; the
users are marked verified and active so they can log in immediately.

Run:  python manage.py populate_db            (idempotent, safe to re-run)
      python manage.py populate_db --flush    (wipe seeded rows first)
      python manage.py populate_db --seed 7   (different but reproducible data)
"""

import random
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from tarcom.base.models import (
    CustomUser,
    Material,
    MaterialCategory,
    Order,
    OrderItem,
    UnitOfMeasure,
)
from tarcom.utils.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    UserType,
)

PASSWORD = "Passw0rd!123"

ICON_DIR = Path(settings.BASE_DIR) / "base" / "static" / "assets" / "images" / "categories"

UNITS = [
    ("EA", "Each", "حبة"),
    ("BX", "Box", "صندوق"),
]

CATEGORIES = [
    ("Laptops", "لابتوبات", "laptop.jpg"),
    ("Batteries", "بطاريات", "batteries.jpg"),
    ("Solar Boards", "ألواح الطاقة الشمسية", "solar_panels.jpg"),
    ("Cables", "كابلات", "usb_cable.jpg"),
    ("Home Tech", "الأجهزة المنزلية الذكية", "home_tech.jpg"),
]

MATERIALS = [
    {
        "name_en": "Dell XPS 15",
        "name_ar": "لابتوب ديل XPS 15",
        "desc_en": "15.6-inch OLED creator laptop with 13th-gen Intel Core i7.",
        "desc_ar": "لابتوب بشاشة OLED مقاس 15.6 بوصة للمبدعين بمعالج إنتل كور i7 من الجيل الثالث عشر.",
        "category": 0,
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
        "desc_en": "Thin and light 13.6-inch laptop powered by the Apple M3 chip.",
        "desc_ar": "لابتوب نحيف وخفيف بشاشة 13.6 بوصة يعمل بشريحة أبل M3.",
        "category": 0,
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
        "desc_en": "High-drain rechargeable 18650 lithium-ion cell, sold in boxes.",
        "desc_ar": "خلية ليثيوم أيون قابلة لإعادة الشحن عالية التصريف 18650، تُباع بالصندوق.",
        "category": 1,
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
        "desc_en": "AGM lead-acid deep-cycle battery for solar and backup systems.",
        "desc_ar": "بطارية حمضية AGM عميقة التفريغ لأنظمة الطاقة الشمسية والأنظمة الاحتياطية.",
        "category": 1,
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
        "desc_en": "200-watt monocrystalline solar panel with high cell efficiency.",
        "desc_ar": "لوح طاقة شمسية أحادي التبلور بقدرة 200 واط بكفاءة خلايا عالية.",
        "category": 2,
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
        "desc_en": "30-amp MPPT solar charge controller with auto system voltage.",
        "desc_ar": "منظم شحن شمسي بتقنية MPPT بتيار 30 أمبير مع جهد نظام تلقائي.",
        "category": 2,
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
        "desc_en": "Braided 100W power-delivery USB-C cable with USB 3.2 data.",
        "desc_ar": "كابل USB-C مضفر باستطاعة 100 واط للشحن السريع مع نقل بيانات USB 3.2.",
        "category": 3,
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
        "desc_en": "Ultra-high-speed HDMI 2.1 cable supporting 8K at 60Hz.",
        "desc_ar": "كابل HDMI 2.1 فائق السرعة يدعم دقة 8K بمعدل 60 هرتز.",
        "category": 3,
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
        "desc_en": "Wi-Fi enabled split inverter air conditioner, 18000 BTU.",
        "desc_ar": "مكيف هواء سبليت انفرتر يدعم الواي فاي، 18000 وحدة حرارية.",
        "category": 4,
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
        "desc_en": "500-litre frost-free smart refrigerator with touch display.",
        "desc_ar": "ثلاجة ذكية بسعة 500 لتر بدون ثلج مع شاشة تعمل باللمس.",
        "category": 4,
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
        categories = self._seed_categories()
        materials = self._seed_materials(uoms, categories)
        users = self._seed_users()
        order_count = self._seed_orders(users, materials, rng)

        self.stdout.write(self.style.SUCCESS(
            f"Populated: {len(uoms)} units, {len(categories)} categories, "
            f"{len(materials)} materials, {len(users)} users, {order_count} orders."
        ))

    def _flush(self):
        OrderItem.objects.all().delete()
        Order.objects.all().delete()
        Material.objects.all().delete()
        MaterialCategory.objects.all().delete()
        UnitOfMeasure.objects.all().delete()
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

    def _seed_categories(self):
        categories = []
        for name_en, name_ar, icon_filename in CATEGORIES:
            category, _ = MaterialCategory.objects.update_or_create(
                name_en=name_en,
                defaults={"name": name_en, "name_ar": name_ar},
            )
            if not category.icon:
                icon_path = ICON_DIR / icon_filename
                if icon_path.exists():
                    with icon_path.open("rb") as f:
                        category.icon.save(icon_filename, File(f), save=True)
            categories.append(category)
        return categories

    def _seed_materials(self, uoms, categories):
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

    def _seed_orders(self, users, materials, rng):
        statuses = list(OrderStatus)
        methods = list(PaymentMethod)
        order_count = 0
        for user in users:
            for i in range(3):
                if Order.objects.filter(user=user).count() > i:
                    order_count += 1
                    continue

                order = Order.objects.create(
                    user=user,
                    status=rng.choice(statuses),
                    payment_method=rng.choice(methods),
                    payment_status=rng.choice(list(PaymentStatus)),
                    shipping_address=rng.choice(ADDRESSES),
                    shipping_phone=user.phone,
                    notes=f"Seed order #{i + 1} for {user.email}",
                )
                for material in rng.sample(materials, k=rng.randint(1, 2)):
                    OrderItem.objects.create(
                        order=order,
                        material=material,
                        quantity=Decimal(rng.randint(1, 5)),
                    )
                order_count += 1
        return order_count
