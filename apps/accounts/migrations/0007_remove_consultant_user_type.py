from django.db import migrations, models


def convert_consultant_accounts_to_customers(apps, schema_editor):
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.filter(user_type='consultant').update(user_type='customer')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_contactmessage_admin_reply_contactmessage_is_replied_and_more'),
    ]

    operations = [
        migrations.RunPython(
            convert_consultant_accounts_to_customers,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='customuser',
            name='user_type',
            field=models.CharField(
                choices=[
                    ('customer', 'Customer'),
                    ('supplier', 'Supplier'),
                    ('admin', 'Admin'),
                ],
                default='customer',
                max_length=20,
            ),
        ),
    ]
