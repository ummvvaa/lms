from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def bind_tokens_and_confirm_school_mail(apps, schema_editor):
    """Ссылки — учётной записи, почта школы — подтверждена.

    Выпущенные до этого ссылки знали только адрес: привязываем их к
    учётной записи с этой почтой. Идентичность «почта и пароль» — это
    почта школы, её подтвердила школа. Личные почты (`email_link`) остаются
    неподтверждёнными: до сих пор их привязывали без письма.
    """
    User = apps.get_model("accounts", "User")
    Token = apps.get_model("accounts", "MagicLinkToken")
    Identity = apps.get_model("accounts", "Identity")
    Token.objects.filter(user__isnull=True).update(
        user=Subquery(User.objects.filter(email__iexact=OuterRef("email")).values("pk")[:1])
    )
    Identity.objects.filter(provider="password", confirmed_at__isnull=True).update(confirmed_at=models.F("created_at"))


class Migration(migrations.Migration):
    """Вход без почты: логин у учётной записи, ссылки — учётной записи,
    личная почта — после подтверждения письмом."""

    dependencies = [
        ("accounts", "0009_teacher_role_and_fictional_flag"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(blank=True, max_length=254, null=True, unique=True, verbose_name="Email"),
        ),
        migrations.AddField(
            model_name="user",
            name="login",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True, verbose_name="Логин"),
        ),
        migrations.AddField(
            model_name="identity",
            name="confirmed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Подтверждена"),
        ),
        migrations.AlterField(
            model_name="magiclinktoken",
            name="email",
            field=models.EmailField(blank=True, db_index=True, max_length=254, verbose_name="Email"),
        ),
        migrations.AddField(
            model_name="magiclinktoken",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="link_tokens",
                to="accounts.user",
                verbose_name="Учётная запись",
            ),
        ),
        migrations.AlterField(
            model_name="magiclinktoken",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("login", "Вход по ссылке"),
                    ("invite", "Приглашение: установить пароль"),
                    ("reset", "Сброс пароля"),
                    ("confirm", "Подтверждение личной почты"),
                ],
                default="login",
                max_length=16,
                verbose_name="Назначение",
            ),
        ),
        migrations.AlterField(
            model_name="loginattempt",
            name="email",
            field=models.CharField(db_index=True, max_length=254, verbose_name="Почта или логин"),
        ),
        migrations.RunPython(bind_tokens_and_confirm_school_mail, migrations.RunPython.noop),
    ]
