"""Свои кнопки, чипы, таблицы, поля и пустые состояния мимо общих компонентов.

Общие компоненты нового языка собраны по образцам один раз: `Button` из
реестра и кнопки внутри `Row`, `DataCard`, `ScreenHead`; чип состояния —
`Chip`; таблица — `DataTable` и `Matrix`; поле — `Field` и `RowForm`; пустое
состояние — `EmptyNote` в живой карточке и `DataCard empty` для карточки
целиком. Сырой тег в экране рядом с ними — вторая кнопка, второй чип,
вторая таблица: на соседних экранах они расходятся на пиксель, а в тёмной
теме и на телефоне — на целую строку.

Что считается (по файлам `screens/**/*.tsx` и `components/**/*.tsx`, кроме
реестра `components/ui/` и самих общих компонентов):

* `button` — сырой `<button`;
* `badge` — прямой `<Badge` вместо `Chip`;
* `table` — сырой `<table`;
* `field` — сырые `<input`, `<select`, `<textarea` вне `Field`, `RowForm`
  и `SelectField` (обёртка списка, которой пользуется `Field`);
* `empty` — свой `<p>` или `<div>` с одной фразой пустоты из
  `test_empty_states.PHRASES`, написанный мимо `EmptyNote` и `DataCard empty`.

Долг записан по файлам: путь от `frontend/src` → число позиций. Файл без
записи обязан быть чистым, записанный — не хуже записанного, закрытое
вычёркивается (`test_the_debt_only_shrinks`). Экраны куратора
(`screens/curator/`) стоят отдельным списком `CURATOR_DEBT`: он закрывается
при переводе экранов куратора на общие компоненты, и после этого остаётся
пустым. Пересчёт — `docker compose exec backend python -m core.tests.test_components_guard`.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.tests.test_empty_states import PHRASES

ROOT = Path("/repo") if Path("/repo/frontend").is_dir() else Path(__file__).resolve().parents[3]
SRC = ROOT / "frontend" / "src"

#: реестр shadcn: сырые теги — его устройство, а не наш экран
REGISTRY = "components/ui/"

#: сами общие компоненты: кнопка и таблица внутри них — и есть общая кнопка и таблица
SHARED = frozenset(
    {
        "components/ui.tsx",
        "components/patterns.tsx",
        "components/DataTable.tsx",
        "components/Empty.tsx",
        "components/Field.tsx",
        "components/EditDrawer.tsx",
        "components/Matrix.tsx",
        "components/WizardSteps.tsx",
        "components/Progress.tsx",
        "components/CalendarCell.tsx",
    }
)

#: где поле ввода — сам общий компонент поля
FIELD_HOMES = frozenset({"components/RowForm.tsx", "components/SelectField.tsx"})

CURATOR = "screens/curator/"

#: свой абзац пустоты: `<p>` или `<div>` с одной переведённой фразой внутри
EMPTY = re.compile(r"<(p|div)\b[^>]*>\s*\{t\('([^']*)'\)\}\s*</\1>")

RULES: dict[str, tuple[re.Pattern[str], str]] = {
    "button": (re.compile(r"<button\b"), "сырая кнопка — `Button` из реестра или кнопка общего компонента"),
    "badge": (re.compile(r"<Badge\b"), "прямой `Badge` — чип состояния пишется через `Chip`"),
    "table": (re.compile(r"<table\b"), "сырая таблица — `DataTable` или `Matrix`"),
    "field": (re.compile(r"<(?:input|select|textarea)\b"), "сырое поле — `Field` или `RowForm`"),
    "empty": (EMPTY, "свой абзац пустоты — `EmptyNote` в карточке или `DataCard empty`"),
}


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def hits_in(rel: str, text: str) -> list[str]:
    """Находки одного файла: `вид строка`."""
    found: list[str] = []
    for kind, (pattern, _) in RULES.items():
        if kind == "field" and rel in FIELD_HOMES:
            continue
        for match in pattern.finditer(text):
            if kind == "empty" and not any(phrase in match.group(2).lower() for phrase in PHRASES):
                continue
            found.append(f"{kind} {_line_of(text, match.start())}")
    return found


def watched() -> list[Path]:
    """Экраны и компоненты, кроме реестра и самих общих компонентов."""
    paths: list[Path] = []
    for folder in ("screens", "components"):
        for path in sorted((SRC / folder).rglob("*.tsx")):
            rel = path.relative_to(SRC).as_posix()
            if rel.startswith(REGISTRY) or rel in SHARED:
                continue
            paths.append(path)
    return paths


def current_debt() -> dict[str, list[str]]:
    """Находки по файлам: путь от `frontend/src` → список `вид строка`."""
    found: dict[str, list[str]] = {}
    for path in watched():
        rel = path.relative_to(SRC).as_posix()
        hits = hits_in(rel, path.read_text("utf-8"))
        if hits:
            found[rel] = hits
    return found


def _breakdown(hits: list[str]) -> str:
    kinds: dict[str, int] = {}
    for hit in hits:
        kind = hit.split(" ")[0]
        kinds[kind] = kinds.get(kind, 0) + 1
    return ", ".join(f"{kind} {count}" for kind, count in sorted(kinds.items()))


#: долг по файлам на 2026-09-26: путь от `frontend/src` → число позиций
#: (кнопки, чипы, таблицы, поля и абзацы пустоты вместе). Заполнен
#: `current_debt()`, не руками. Только уменьшается
DEBT: dict[str, int] = {
    "components/AdmissionBlock.tsx": 1,  # badge 1
    "components/AssistantWidget.tsx": 11,  # badge 3, button 7, field 1
    "components/BadgesBlock.tsx": 1,  # badge 1
    "components/CalendarCard.tsx": 4,  # button 4
    "components/ConfirmDialog.tsx": 1,  # badge 1
    "components/CredentialsBox.tsx": 1,  # table 1
    "components/CuratorNotesBlock.tsx": 1,  # badge 1
    "components/DeleteButton.tsx": 1,  # button 1
    "components/EnrollPanel.tsx": 4,  # badge 2, field 1, table 1
    "components/ExamGoals.tsx": 1,  # table 1
    "components/ExamResults.tsx": 3,  # badge 2, table 1
    "components/ExportPreview.tsx": 1,  # table 1
    "components/GettingStarted.tsx": 2,  # badge 1, button 1
    "components/HandoutDialog.tsx": 1,  # badge 1
    "components/ImportHistory.tsx": 3,  # badge 2, table 1
    "components/ImportWizard.tsx": 18,  # badge 14, button 1, field 1, table 2
    "components/JobsPanel.tsx": 1,  # button 1
    "components/LetterDialog.tsx": 3,  # badge 3
    "components/LinkIdentityBanner.tsx": 1,  # badge 1
    "components/LoginLocks.tsx": 1,  # badge 1
    "components/MatchCard.tsx": 3,  # badge 3
    "components/MaterialCard.tsx": 6,  # badge 6
    "components/Notice.tsx": 1,  # button 1
    "components/Notifications.tsx": 2,  # button 2
    "components/OpenAnswers.tsx": 1,  # badge 1
    "components/PendingQueue.tsx": 5,  # badge 4, button 1
    "components/PlatformMocks.tsx": 4,  # badge 3, table 1
    "components/ProgramList.tsx": 4,  # badge 4
    "components/QuestionForm.tsx": 3,  # badge 2, field 1
    "components/QuestionsImport.tsx": 4,  # badge 3, field 1
    "components/RequirementsImport.tsx": 8,  # badge 5, field 1, table 2
    "components/RowForm.tsx": 1,  # badge 1
    "components/RowsImport.tsx": 8,  # badge 6, field 1, table 1
    "components/ScholarshipsImport.tsx": 8,  # badge 5, field 1, table 2
    "components/SelectField.tsx": 2,  # button 2
    "components/StepDone.tsx": 1,  # button 1
    "components/StudentQueue.tsx": 6,  # badge 5, button 1
    "components/StudentRegistry.tsx": 1,  # button 1
    "components/StudentRegistryCard.tsx": 1,  # badge 1
    "components/StudentRows.tsx": 1,  # badge 1
    "components/StudyGroups.tsx": 3,  # badge 2, empty 1
    "components/TodayPanel.tsx": 6,  # badge 6
    "screens/Achievements.tsx": 1,  # badge 1
    "screens/AiPanels.tsx": 8,  # badge 7, field 1
    "screens/Archive.tsx": 1,  # badge 1
    "screens/Assistant.tsx": 14,  # badge 11, button 2, field 1
    "screens/Attendance.tsx": 5,  # badge 3, button 1, table 1
    "screens/Calendar.tsx": 5,  # badge 4, button 1
    "screens/CallRules.tsx": 4,  # badge 3, table 1
    "screens/Career.tsx": 4,  # badge 2, button 1, empty 1
    "screens/CareerQuestions.tsx": 3,  # badge 2, table 1
    "screens/Catalog.tsx": 9,  # badge 6, field 3
    "screens/ChangePassword.tsx": 6,  # badge 3, field 3
    "screens/Contacts.tsx": 1,  # badge 1
    "screens/Digest.tsx": 4,  # badge 2, button 1, table 1
    "screens/Directory.tsx": 1,  # badge 1
    "screens/DirectoryList.tsx": 5,  # badge 4, table 1
    "screens/EssayContent.tsx": 1,  # button 1
    "screens/Essays.tsx": 7,  # badge 3, button 3, empty 1
    "screens/Favorites.tsx": 1,  # badge 1
    "screens/ImportScreen.tsx": 9,  # badge 6, field 1, table 2
    "screens/Journey.tsx": 4,  # badge 4
    "screens/Login.tsx": 4,  # badge 2, field 2
    "screens/MailTemplates.tsx": 1,  # badge 1
    "screens/Materials.tsx": 20,  # badge 15, button 4, field 1
    "screens/MyData.tsx": 14,  # badge 12, field 2
    "screens/MyDocuments.tsx": 6,  # badge 4, button 1, field 1
    "screens/MyUniversities.tsx": 2,  # badge 2
    "screens/OlympiadGroup.tsx": 3,  # badge 2, table 1
    "screens/Onboarding.tsx": 1,  # badge 1
    "screens/Plan.tsx": 3,  # badge 2, button 1
    "screens/Prep.tsx": 16,  # badge 8, button 7, table 1
    "screens/Profile.tsx": 9,  # badge 4, button 2, field 3
    "screens/Quiz.tsx": 3,  # badge 1, button 1, table 1
    "screens/Resources.tsx": 8,  # badge 7, button 1
    "screens/Roadmap.tsx": 6,  # badge 6
    "screens/ScholarshipDirectory.tsx": 3,  # badge 2, table 1
    "screens/Scholarships.tsx": 11,  # badge 11
    "screens/Selection.tsx": 5,  # badge 4, button 1
    "screens/SetPassword.tsx": 4,  # badge 2, field 2
    "screens/Spend.tsx": 6,  # badge 3, table 3
    "screens/StudentCard.tsx": 5,  # badge 3, field 1, table 1
    "screens/SuggestionPreview.tsx": 6,  # badge 5, table 1
    "screens/Suggestions.tsx": 2,  # badge 1, table 1
    "screens/TableScreen.tsx": 10,  # badge 4, button 3, field 2, table 1
    "screens/Users.tsx": 9,  # badge 6, button 2, table 1
    "screens/dashboards/AdminDashboard.tsx": 3,  # badge 2, table 1
    "screens/dashboards/AdmissionDashboard.tsx": 3,  # badge 3
    "screens/dashboards/BehaviorDashboard.tsx": 2,  # badge 1, button 1
    "screens/dashboards/ExamDashboard.tsx": 2,  # badge 1, button 1
    "screens/dashboards/SportDashboard.tsx": 1,  # badge 1
    "screens/dashboards/StudentHome.tsx": 5,  # badge 3, button 2
    "screens/dashboards/TalentDashboard.tsx": 1,  # badge 1
    "screens/sections/Competitions.tsx": 2,  # badge 1, button 1
    "screens/sections/Deadlines.tsx": 1,  # badge 1
    "screens/sections/Groups.tsx": 2,  # badge 2
    "screens/sections/Mocks.tsx": 1,  # badge 1
    "screens/sections/Risks.tsx": 2,  # badge 2
}

#: долг экранов куратора — закрыть при переводе экранов куратора на общие
#: компоненты; после этого список пуст и таким остаётся
CURATOR_DEBT: dict[str, int] = {
    "screens/curator/Card.tsx": 5,  # badge 5
    "screens/curator/Dialogs.tsx": 1,  # badge 1
    "screens/curator/DirectEntry.tsx": 1,  # badge 1
    "screens/curator/DisciplineBlock.tsx": 1,  # badge 1
    "screens/curator/DocumentPreview.tsx": 2,  # badge 1, button 1
    "screens/curator/Documents.tsx": 3,  # button 2, table 1
    "screens/curator/GroupSwitch.tsx": 1,  # button 1
    "screens/curator/Home.tsx": 1,  # badge 1
    "screens/curator/Journal.tsx": 1,  # table 1
    "screens/curator/MockImports.tsx": 6,  # badge 2, button 2, table 2
    "screens/curator/MockWizard.tsx": 8,  # badge 3, button 2, field 1, table 2
    "screens/curator/Queue.tsx": 1,  # button 1
    "screens/curator/Students.tsx": 6,  # badge 2, button 3, table 1
    "screens/curator/TaskDialog.tsx": 1,  # button 1
    "screens/curator/Tasks.tsx": 1,  # button 1
}


def ledger_of(rel: str) -> dict[str, int]:
    return CURATOR_DEBT if rel.startswith(CURATOR) else DEBT


def test_screens_use_shared_components_except_the_listed_debt():
    """Файл без записи в долге чист, записанный — не хуже записанного."""
    found = current_debt()
    worse = {rel: hits for rel, hits in found.items() if len(hits) > ledger_of(rel).get(rel, 0)}
    assert not worse, (
        "свои теги мимо общих компонентов: "
        + "; ".join(f"{rel} ({_breakdown(hits)}, в долге {ledger_of(rel).get(rel, 0)})" for rel, hits in worse.items())
        + ". "
        + "; ".join(hint for _, hint in RULES.values())
    )


def test_curator_screens_are_clean_or_listed_separately():
    """Экраны куратора — в своём списке: там долг закрывается первым."""
    found = current_debt()
    stray = sorted(rel for rel in found if rel.startswith(CURATOR) and rel not in CURATOR_DEBT)
    assert not stray, f"экраны куратора мимо CURATOR_DEBT: {stray}"
    misplaced = sorted(rel for rel in DEBT if rel.startswith(CURATOR))
    assert not misplaced, f"экраны куратора перечисляются в CURATOR_DEBT, не в DEBT: {misplaced}"


def test_the_debt_only_shrinks():
    """Закрытое вычёркивается из списка, сокращённое — записывается новым числом."""
    found = current_debt()
    paid = {
        rel: len(found.get(rel, []))
        for ledger in (DEBT, CURATOR_DEBT)
        for rel in ledger
        if len(found.get(rel, [])) < ledger[rel]
    }
    assert not paid, "долг сокращён — впишите новые числа (ноль — вычеркните): " + ", ".join(
        f"{rel}: {ledger_of(rel)[rel]} → {count}" for rel, count in sorted(paid.items())
    )


def test_the_scan_catches_planted_tags():
    """Сама проверка ловит подложенный тег — иначе она ничего не значит."""
    assert hits_in("screens/X.tsx", '<button type="button">x</button>') == ["button 1"]
    assert hits_in("screens/X.tsx", "<Button>x</Button>") == []
    assert hits_in("screens/X.tsx", '<Badge variant="ok">x</Badge>\n<Chip>y</Chip>') == ["badge 1"]
    assert hits_in("screens/X.tsx", '<table className="tbl">') == ["table 1"]
    assert hits_in("screens/X.tsx", "<Table>") == []
    assert hits_in("screens/X.tsx", '<input\n  type="text"\n/>\n<select>\n<textarea />') == [
        "field 1",
        "field 4",
        "field 5",
    ]
    assert hits_in("components/RowForm.tsx", '<input type="text" />') == []
    assert hits_in("screens/X.tsx", "<p className=\"muted\">{t('Заметок пока нет')}</p>") == ["empty 1"]
    assert hits_in("screens/X.tsx", "<div className=\"x\">\n  {t('Список пуст')}\n</div>") == ["empty 1"]
    assert hits_in("screens/X.tsx", "<p className=\"muted\">{t('Сохранено')}</p>") == []
    assert hits_in("screens/X.tsx", '<EmptyNote what="пока нет" />') == []


if __name__ == "__main__":
    # пересчёт долга для вставки в DEBT и CURATOR_DEBT
    for rel, hits in sorted(current_debt().items()):
        print(f'    "{rel}": {len(hits)},  # {_breakdown(hits)}')
