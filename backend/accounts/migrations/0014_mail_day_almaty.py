from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0013_invite_mail_queue")]

    operations = [
        migrations.AlterField(
            model_name="maildaybudget",
            name="day",
            field=models.DateField(primary_key=True, serialize=False, verbose_name="Сутки по Алматы"),
        ),
    ]
