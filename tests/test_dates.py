import re
from datetime import date, datetime
from pathlib import Path

import pytest

from people_memory.dates import PARTIAL_DATE_PATTERN, normalize_partial_date

MIGRATIONS = Path(__file__).parents[1] / "supabase" / "migrations"


def test_full_dates_render_as_iso() -> None:
    assert normalize_partial_date(date(2022, 4, 1)) == "2022-04-01"
    assert normalize_partial_date(datetime(2022, 4, 1, 13, 30)) == "2022-04-01"
    assert normalize_partial_date("2022-04-01") == "2022-04-01"


def test_partial_dates_survive_at_the_precision_they_were_given() -> None:
    assert normalize_partial_date("2015-10") == "2015-10"
    assert normalize_partial_date("2015") == "2015"


def test_nothing_recorded_stays_nothing() -> None:
    assert normalize_partial_date(None) is None
    assert normalize_partial_date("") is None
    assert normalize_partial_date("   ") is None


@pytest.mark.parametrize(
    "value",
    [
        "01 Apr 2022",  # LinkedIn's own export format, silently stored as text once
        "2019-2020",  # a range, which belongs in a text value next to the fact
        "ongoing",
        "04/01/2022",
        "2022-4-1",  # unpadded, so it would sort wrong against its neighbours
    ],
)
def test_anything_that_is_not_a_date_raises_instead_of_becoming_null(value: str) -> None:
    """Storing NULL here would hide a parsing bug: the caller thinks the date was saved."""
    with pytest.raises(ValueError, match="not a date"):
        normalize_partial_date(value)


@pytest.mark.parametrize("value", ["2022-13", "2022-02-30", "2022-00-01"])
def test_right_shape_but_not_a_real_date_raises(value: str) -> None:
    with pytest.raises(ValueError, match="not a real date"):
        normalize_partial_date(value)


def test_iso_prefixes_sort_as_text_in_calendar_order() -> None:
    """The whole reason these live in text: ordering must not need a cast to be correct."""
    values = ["2024", "2015-10", "2022", "2015-10-01", "2015-09-30"]
    assert sorted(values) == ["2015-09-30", "2015-10", "2015-10-01", "2022", "2024"]


def test_python_and_postgres_agree_on_what_is_storable() -> None:
    """A pattern that drifts means one side rejects what the other just accepted."""
    sql = "\n".join(path.read_text(encoding="utf-8") for path in MIGRATIONS.glob("*.sql"))
    in_sql = set(re.findall(r"'(\^\\d\{4\}[^']*)'", sql))
    assert in_sql, "no partial-date pattern found in the migrations"
    assert in_sql == {PARTIAL_DATE_PATTERN}, in_sql
