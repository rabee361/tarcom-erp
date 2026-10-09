from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0009_material_feature_reason_material_is_feature'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='materialcategory',
            name='icon',
        ),
    ]
