from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0010_remove_materialcategory_icon'),
    ]

    operations = [
        migrations.AddField(
            model_name='material',
            name='company',
            field=models.CharField(default='', max_length=100),
            preserve_default=False,
        ),
    ]
