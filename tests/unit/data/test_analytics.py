"""Hand-calculated checks of the descriptive analytics. All inputs are SYNTHETIC_TEST_DATA."""

from datetime import date
from decimal import Decimal

import pytest

from quantlab.data.analytics import (
    average_volume,
    rebased_comparison,
    session_return,
    simple_return,
    weekday_gap_ranges,
)

D = Decimal


def test_simple_return_is_rounded_half_even_to_eight_places() -> None:
    assert simple_return(D("110"), D("100")) == D("0.10000000")
    assert simple_return(D("95"), D("100")) == D("-0.05000000")
    # 100 / 3 - 1 = 32.333333333...
    assert simple_return(D("100"), D("3")) == D("32.33333333")
    # 2 / 3 - 1 = -0.3333333333...
    assert simple_return(D("2"), D("3")) == D("-0.33333333")


def test_session_return_uses_the_close_n_sessions_back() -> None:
    closes = [D("100"), D("102"), D("101"), D("105")]

    assert session_return(closes, 1) == simple_return(D("105"), D("101"))
    assert session_return(closes, 3) == D("0.05000000")


def test_session_return_is_none_without_enough_history() -> None:
    assert session_return([D("100"), D("102")], 2) is None
    assert session_return([D("100")], 1) is None
    assert session_return([], 1) is None
    with pytest.raises(ValueError, match="at least 1"):
        session_return([D("1"), D("2")], 0)


def test_average_volume_covers_exactly_the_last_n_sessions() -> None:
    assert average_volume([1000, 10, 20, 31], 3) == D("20.33")  # 61 / 3 = 20.333...
    assert average_volume([10, 20, 30], 3) == D("20.00")
    assert average_volume([10, 20], 3) is None


def test_gap_ranges_count_missing_weekdays_and_skip_weekends() -> None:
    dates = [
        date(2024, 1, 1),  # Mon
        date(2024, 1, 2),  # Tue
        date(2024, 1, 5),  # Fri: Wed 3 and Thu 4 missing
        date(2024, 1, 8),  # Mon: only the weekend between, not a gap
        date(2024, 1, 16),  # Tue: Tue 9 to Mon 15 missing = 5 weekdays
    ]

    gaps = weekday_gap_ranges(dates)

    assert [(g.start, g.end, g.missing_weekdays) for g in gaps] == [
        (date(2024, 1, 3), date(2024, 1, 4), 2),
        (date(2024, 1, 9), date(2024, 1, 15), 5),
    ]
    assert weekday_gap_ranges([]) == []
    assert weekday_gap_ranges([date(2024, 1, 1)]) == []


def test_comparison_rebases_both_series_to_100_on_the_first_common_session() -> None:
    base = [
        (date(2024, 1, 1), D("50")),  # before the other series starts
        (date(2024, 1, 2), D("200")),
        (date(2024, 1, 3), D("210")),
        (date(2024, 1, 4), D("190")),
        (date(2024, 1, 5), D("220")),
    ]
    other = [
        (date(2024, 1, 2), D("40")),
        (date(2024, 1, 4), D("30")),  # no bar on 3 Jan
        (date(2024, 1, 5), D("44")),
        (date(2024, 1, 8), D("99")),  # after the base series ends
    ]

    result = rebased_comparison(base, other)

    assert result.base_date == date(2024, 1, 2)
    assert [(p.trading_date, p.base_index, p.comparison_index) for p in result.points] == [
        (date(2024, 1, 2), D("100.000000"), D("100.000000")),
        (date(2024, 1, 4), D("95.000000"), D("75.000000")),
        (date(2024, 1, 5), D("110.000000"), D("110.000000")),
    ]
    # 3 Jan is inside the overlap and only the base has it. 1 Jan and 8 Jan are outside.
    assert (result.base_only_sessions, result.comparison_only_sessions) == (1, 0)


def test_comparison_without_common_sessions_is_empty() -> None:
    result = rebased_comparison([(date(2024, 1, 1), D("1"))], [(date(2024, 1, 2), D("1"))])

    assert result.base_date is None
    assert result.points == ()
