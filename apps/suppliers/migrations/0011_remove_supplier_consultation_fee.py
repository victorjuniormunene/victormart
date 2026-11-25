from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('suppliers', '0010_supplier_subscription_expires_at_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='supplier',
            name='consultation_fee',
        ),
    ]
