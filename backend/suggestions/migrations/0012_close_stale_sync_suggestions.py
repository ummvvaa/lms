"""Закрыть накопленные предложения ночной сверки дедлайнов (D47).

До правки нерешённое расхождение каждую ночь ложилось новым предложением —
у директора по поступлению их набралось шестнадцать одинаковых. Сверка теперь
держит одно предложение на вуз и обновляет его; старые закрываются как
устаревшие, а ближайшая ночная сверка заведёт свежие — по одному на вуз.

Пишем через `update()`: это не решение человека, журнал правок полей не нужен —
сами поля справочника миграция не трогает.
"""

from django.db import migrations
from django.utils import timezone

REASON = "Устарело: заменено новой сверкой"


def close_stale(apps, schema_editor):
    Suggestion = apps.get_model("suggestions", "Suggestion")
    Suggestion.objects.filter(source_type="web_sync", command="sync_deadlines", status="pending").update(
        status="rejected", reject_reason=REASON, resolved_at=timezone.now()
    )


class Migration(migrations.Migration):
    dependencies = [("suggestions", "0011_superseded_by_curator")]

    operations = [migrations.RunPython(close_stale, migrations.RunPython.noop)]
