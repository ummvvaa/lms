"""Русские исходники с переводом — для проверки перевода в каталоге экранов.

    python3 build_i18n_keys.py   # → shots/i18n-keys.json

Ключ попадает в список языка, если его перевод на этот язык отличается от
исходника: такая строка на экране казахского или английского интерфейса
значит, что перевод не дошёл. Источники — словари фронта и каталог сервера.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core import translations  # noqa: E402


def po_entries(lang: str) -> dict[str, str]:
    text = (ROOT / "backend" / "locale" / lang / "LC_MESSAGES" / "django.po").read_text(encoding="utf-8")
    out = {}
    for block in text.split("\n\n"):
        msgid = re.search(r'^msgid "(.*)"$', block, re.M)
        msgstr = re.search(r'^msgstr "(.*)"$', block, re.M)
        if msgid and msgstr and msgid.group(1):
            out[json.loads(f'"{msgid.group(1)}"')] = json.loads(f'"{msgstr.group(1)}"')
    return out


result = {}
dictionaries = translations.read_dictionaries(ROOT / "frontend" / "src" / "i18n")
for lang in translations.LANGS:
    pairs = {**po_entries(lang), **dictionaries[lang].entries}
    # короткие общие слова («да», «нет», «из») в данных встречаются законно — только фразы от 3 букв
    result[lang] = sorted(
        key for key, value in pairs.items() if value and value != key and len(key.strip()) >= 3
    )
out = Path(__file__).resolve().parent / "shots" / "i18n-keys.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
print({lang: len(rows) for lang, rows in result.items()})
