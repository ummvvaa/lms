"""Полный предпросмотр сохраняет все строки и результат их применения."""

from collections import Counter

import pytest

from universities.import_requirements import import_requirements
from universities.import_scholarships import import_scholarships
from universities.models import AdmissionRequirement, Scholarship


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["requirements", "scholarships"])
def test_preview_includes_rows_after_fifty_errors_and_unchanged_records(kind):
    if kind == "requirements":
        run = import_requirements
        model = AdmissionRequirement
        header = ["university", "program", "min_ielts"]
        initial = [["Test University", "Updated", "5"], ["Test University", "Unchanged", "5"]]
        new = [["Test University", f"Program {number}", "6"] for number in range(59)]
        changed = [["Test University", "Updated", "6"], initial[1]]
        broken = [["", "No university", "6"], ["Test University", "Bad score", "invalid"]]
    else:
        run = import_scholarships
        model = Scholarship
        header = ["name", "organizer", "amount_min"]
        initial = [["Updated", "Test Fund", "500"], ["Unchanged", "Test Fund", "500"]]
        new = [[f"Scholarship {number}", "Test Fund", "600"] for number in range(59)]
        changed = [["Updated", "Test Fund", "600"], initial[1]]
        broken = [["", "Test Fund", "600"], ["Bad amount", "Test Fund", "invalid"]]
    mapping = {name: name for name in header}
    run(header=header, rows=initial, mapping=mapping)
    before = model.objects.count()
    rows = new + changed + broken

    preview = run(header=header, rows=rows, mapping=mapping, dry_run=True).as_dict()

    assert model.objects.count() == before
    assert len(preview["rows"]) == len(rows)
    assert [row["row"] for row in preview["rows"]] == list(range(2, len(rows) + 2))
    assert Counter(row["status"] for row in preview["rows"]) == {
        "created": 59,
        "updated": 1,
        "skipped": 1,
        "error": 2,
    }
    assert [row["reason"] for row in preview["rows"] if row["status"] == "error"] == preview["errors"]

    applied = run(header=header, rows=rows, mapping=mapping).as_dict()
    assert model.objects.count() == before + 59
    assert applied == preview
