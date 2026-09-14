"""Фаза 73: блок «Поступление» — один компонент, одни стили у трёх ролей.

Состав блока у куратора, Асем и администратора проверяет фаза 70. Здесь —
вид: блок рендерится **одним** компонентом на обеих карточках, а его стили
лежат в файле, который приложение грузит целиком, — не в `curator.css`,
которого карточка Асем не грузит (так блок и стоял без раскладки).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/frontend").is_dir() else Path(__file__).resolve().parents[3]
SRC = ROOT / "frontend" / "src"


def read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def test_both_cards_render_the_same_component():
    """Карточка сотрудников и карточка куратора импортируют один AdmissionBlock."""
    staff = read("screens/StudentCard.tsx")
    curator = read("screens/curator/Card.tsx")
    assert "from '../components/AdmissionBlock'" in staff
    assert "from '../../components/AdmissionBlock'" in curator
    assert "<AdmissionBlock" in staff and "<AdmissionBlock" in curator


def test_block_styles_live_in_the_shared_stylesheet():
    """Стили `.cadm` — в `ui.css`, который грузит `App.tsx`; в curator.css их нет."""
    assert re.search(r"^\.cadm \{", read("components/ui.css"), re.M)
    assert re.search(r"^\.cadm__pair \{", read("components/ui.css"), re.M)
    assert "import './components/ui.css'" in read("App.tsx")
    assert ".cadm" not in read("screens/curator/curator.css")
    # и никакой другой файл экрана не переопределяет блок втихую
    for path in SRC.rglob("*.css"):
        if path.name != "ui.css":
            assert ".cadm" not in path.read_text(encoding="utf-8"), path


def test_values_never_wrap_inside_themselves():
    """Значение — одной строкой: перенос по буквам запрещён стилем, не удачей."""
    css = read("components/ui.css")
    value = css[css.index(".cadm__v {") : css.index(".cadm__v--mono {")]
    assert "white-space: nowrap" in value
    assert "min-width: 0" in value
    assert "overflow-wrap: anywhere" not in css[css.index(".cadm {") :]


def test_rows_follow_the_table_columns_by_name():
    """Названия и порядок строк — колонки таблицы Асем; ничего сверх."""
    full = read("components/AdmissionBlock.tsx")
    # только разметка самого блока: вспомогательные строки объявлены выше
    source = full[full.index("export default function AdmissionBlock") :]
    labels = [
        "Номер телефона",
        "Электронный адрес",
        "Пароль от эл. адреса",
        "Пароль от Common App",
        "Электронный адрес Common App",
        "Ссылка на папку студента",
        "Ссылка на паспорт",
        "Срок годности паспорта",
        # GPA — своим компонентом, подпись внутри него
        "<GpaRow",
        "Ссылка на табель",
        "Ссылка на рек. письмо",
    ]
    positions = [source.index(label) for label in labels]
    assert positions == sorted(positions), "порядок строк — порядок колонок таблицы"
    assert "срок не указан" not in source
