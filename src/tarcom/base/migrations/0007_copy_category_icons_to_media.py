from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.db import migrations

STATIC_ICON_PREFIX = "assets/images/categories/"


def copy_icons_to_media(apps, schema_editor):
    """Re-point category icons from static paths to real media uploads."""
    MaterialCategory = apps.get_model("base", "MaterialCategory")
    for category in MaterialCategory.objects.all():
        icon = str(category.icon or "")
        if not icon.startswith(STATIC_ICON_PREFIX):
            continue
        source_path = finders.find(icon)
        if not source_path:
            continue
        with open(source_path, "rb") as f:
            category.icon.save(
                icon[len(STATIC_ICON_PREFIX):], ContentFile(f.read()), save=True
            )


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0006_image_fields_to_versatileimagefield"),
    ]

    operations = [
        migrations.RunPython(copy_icons_to_media, migrations.RunPython.noop),
    ]