import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from quantlab.backtesting.costs import (
    CostModelError,
    CostRates,
    CostSchedule,
    CostScheduleEntry,
    ZeroCostModel,
    compute_costs,
    load_cost_schedule,
)
from quantlab.backtesting.engine import run_backtest
from quantlab.backtesting.models import Side
from quantlab.backtesting.strategy import (
    BuyAndHold,
    DecisionContext,
    MovingAverageCrossover,
    simple_moving_average,
)
from tests.backtesting.helpers import D, bar, config, day

NOTE = "SYNTHETIC rates invented for this test; not real charges"


def _entry(start: date, end: date | None, rate: str) -> CostScheduleEntry:
    return CostScheduleEntry(start, end, CostRates(brokerage_rate=D(rate)), NOTE)


def test_rates_are_chosen_by_the_fill_date() -> None:
    schedule = CostSchedule(
        "toy",
        "2",
        [
            _entry(date(2024, 7, 1), None, "0.002"),
            _entry(date(2024, 1, 1), date(2024, 6, 30), "0.001"),
        ],
    )

    assert schedule.model_id == "toy@2"
    assert schedule.costs(Side.BUY, D("10000"), date(2024, 6, 30)).brokerage == D("10.00")
    assert schedule.costs(Side.BUY, D("10000"), date(2024, 7, 1)).brokerage == D("20.00")


def test_a_date_without_rates_is_an_error_not_zero_cost() -> None:
    schedule = CostSchedule("toy", "1", [_entry(date(2024, 1, 1), date(2024, 6, 30), "0.001")])

    with pytest.raises(CostModelError, match="no rates in effect on 2023-12-31"):
        schedule.costs(Side.BUY, D("100"), date(2023, 12, 31))
    with pytest.raises(CostModelError, match="no rates in effect"):
        schedule.costs(Side.BUY, D("100"), date(2024, 7, 1))


def test_invalid_schedules_are_rejected() -> None:
    with pytest.raises(CostModelError, match="overlap"):
        CostSchedule(
            "toy",
            "1",
            [
                _entry(date(2024, 1, 1), date(2024, 6, 30), "0"),
                _entry(date(2024, 6, 30), None, "0"),
            ],
        )
    with pytest.raises(CostModelError, match="overlap"):
        CostSchedule(
            "toy", "1", [_entry(date(2024, 1, 1), None, "0"), _entry(date(2025, 1, 1), None, "0")]
        )
    with pytest.raises(CostModelError, match="at least one"):
        CostSchedule("toy", "1", [])
    with pytest.raises(CostModelError, match="source_note"):
        CostSchedule("toy", "1", [CostScheduleEntry(date(2024, 1, 1), None, CostRates(), " ")])
    with pytest.raises(CostModelError, match="non-negative"):
        CostRates(stt_sell_rate=D("-0.001"))


def test_components_are_rounded_half_even_and_side_specific() -> None:
    rates = CostRates(
        brokerage_rate=D("0.0005"),
        stt_buy_rate=D("0.0001"),
        stt_sell_rate=D("0.00025"),
        exchange_rate=D("0.00005"),
        sebi_rate=D("0.000001"),
        stamp_duty_buy_rate=D("0.00015"),
        gst_rate=D("0.18"),
    )

    buy = compute_costs(rates, Side.BUY, D("12345.00"))
    sell = compute_costs(rates, Side.SELL, D("12345.00"))

    # brokerage 6.1725 -> 6.17 | exchange 0.61725 -> 0.62 | SEBI 0.012345 -> 0.01
    assert (buy.brokerage, buy.exchange_charges, buy.sebi_charges) == (
        D("6.17"),
        D("0.62"),
        D("0.01"),
    )
    # STT buy 1.2345 -> 1.23, sell 3.08625 -> 3.09 | stamp duty 1.85175 -> 1.85, buys only
    assert (buy.stt, sell.stt) == (D("1.23"), D("3.09"))
    assert (buy.stamp_duty, sell.stamp_duty) == (D("1.85"), D("0"))
    # GST 0.18 * (6.17 + 0.62 + 0.01) = 1.224 -> 1.22
    assert buy.gst == sell.gst == D("1.22")
    assert buy.total == D("11.10")
    assert sell.total == D("11.11")
    assert ZeroCostModel().costs(Side.SELL, D("12345"), date(2024, 1, 1)).total == D("0")


def test_schedule_loads_from_json_and_requires_exact_decimal_strings(tmp_path: Path) -> None:
    document = {
        "schedule_id": "toy",
        "version": "3",
        "entries": [
            {
                "effective_from": "2024-01-01",
                "effective_to": None,
                "source_note": NOTE,
                "rates": {
                    "brokerage_rate": "0.001",
                    "brokerage_cap_per_order": "20",
                    "gst_rate": "0.18",
                },
            }
        ],
    }
    path = tmp_path / "costs.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    schedule = load_cost_schedule(path)
    costs = schedule.costs(Side.BUY, D("51510"), date(2024, 5, 1))

    assert schedule.model_id == "toy@3"
    assert (costs.brokerage, costs.gst, costs.stt) == (D("20.00"), D("3.60"), D("0.00"))

    document["entries"][0]["rates"]["brokerage_rate"] = 0.001  # type: ignore[index]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CostModelError, match="written as a string"):
        load_cost_schedule(path)
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(CostModelError, match="invalid cost schedule file"):
        load_cost_schedule(path)


def test_simple_moving_average() -> None:
    closes = [D("10"), D("12"), D("14")]

    assert simple_moving_average(closes, 2) == D("13")
    assert simple_moving_average(closes, 3) == D("12")
    assert simple_moving_average(closes, 4) is None
    with pytest.raises(ValueError, match="at least 1"):
        simple_moving_average(closes, 0)


def test_moving_average_crossover_signals_match_hand_calculation() -> None:
    strategy = MovingAverageCrossover(["X"], fast_window=2, slow_window=3)
    closes = [D(c) for c in ["10", "10", "10", "12", "14", "9", "8"]]

    signals = [strategy.signal(closes[:n]) for n in range(1, len(closes) + 1)]

    # Session 1, 2: fewer than 3 closes, out.
    # Session 3: fast (10+10)/2 = 10, slow 10. Not strictly above, out.
    # Session 4: fast (10+12)/2 = 11, slow 32/3 = 10.67. In.
    # Session 5: fast 13, slow 12. In.
    # Session 6: fast (14+9)/2 = 11.5, slow 35/3 = 11.67. Out.
    # Session 7: fast 8.5, slow 31/3 = 10.33. Out.
    assert signals == [False, False, False, True, True, False, False]


def test_crossover_trades_only_when_signal_and_holding_disagree() -> None:
    strategy = MovingAverageCrossover(["Y", "X"], fast_window=1, slow_window=2)
    rising = [bar(1, "10", "10"), bar(2, "11", "11")]
    falling = [bar(1, "10", "10"), bar(2, "9", "9")]
    history = {"X": rising, "Y": falling}

    def decide(holdings: dict[str, int]) -> dict[str, Decimal]:
        return dict(strategy.decide(DecisionContext(day(2), history, holdings, D("0"), D("0"))))

    # X is "in", Y is "out". Each instrument's share of the universe is 1/2.
    assert decide({}) == {"X": D("0.5")}  # buy X; nothing to do for Y
    assert decide({"X": 10}) == {}  # already in X: no top-up, no trim
    assert decide({"Y": 10}) == {"X": D("0.5"), "Y": D("0")}  # buy X, sell Y
    assert decide({"X": 10, "Y": 10}) == {"Y": D("0")}
    assert strategy.strategy_id == "ma-crossover(fast=1,slow=2,n=2)"


def test_crossover_gives_no_signal_for_an_instrument_without_a_bar_that_day() -> None:
    strategy = MovingAverageCrossover(["X"], fast_window=1, slow_window=2)
    bars = [bar(1, "10", "10"), bar(2, "11", "11")]

    assert strategy.decide(DecisionContext(day(3), {"X": bars}, {"X": 5}, D("0"), D("0"))) == {}
    assert strategy.decide(DecisionContext(day(1), {}, {}, D("0"), D("0"))) == {}


def test_crossover_rejects_bad_parameters() -> None:
    with pytest.raises(ValueError, match="fast_window < slow_window"):
        MovingAverageCrossover(["X"], 5, 5)
    with pytest.raises(ValueError, match="empty"):
        MovingAverageCrossover([], 2, 3)
    with pytest.raises(ValueError, match="duplicates"):
        MovingAverageCrossover(["X", "X"], 2, 3)


def test_crossover_end_to_end_orders_follow_the_signals_one_session_later() -> None:
    closes = ["10", "10", "10", "12", "14", "9", "8", "8"]
    bars = [bar(n, close, close) for n, close in enumerate(closes, start=1)]

    result = run_backtest(
        {"X": bars}, MovingAverageCrossover(["X"], 2, 3), ZeroCostModel(), config("1000")
    )

    # In after session 4 (close 12): floor(1000/12) = 83 shares wanted, filled at session 5
    # open 14 where cash covers floor(1000/14) = 71. Still "in" after session 5 and already
    # held, so no order. Out after session 6: all 71 sold at session 7 open 8.
    assert [(f.fill_date, f.side, f.quantity, f.price) for f in result.fills] == [
        (day(5), Side.BUY, 71, D("14")),
        (day(7), Side.SELL, 71, D("8")),
    ]
    assert result.final_cash == D("574")  # 1000 - 994 + 568
    assert len(result.orders) == 2  # no rebalancing orders in between


def test_buy_and_hold_buys_once_and_never_rebalances() -> None:
    x = [bar(1, "10", "10"), bar(2, "10", "20"), bar(3, "20", "40"), bar(4, "40", "40")]
    y = [bar(n, "10", "10") for n in range(1, 5)]
    benchmark = BuyAndHold({"X": D("0.5"), "Y": D("0.5")})

    result = run_backtest({"X": x, "Y": y}, benchmark, ZeroCostModel(), config("1000"))

    assert [(f.fill_date, f.instrument_id, f.quantity) for f in result.fills] == [
        (day(2), "X", 50),
        (day(2), "Y", 50),
    ]
    # X grows to 80% of the portfolio and is left alone: 50*40 + 50*10 = 2500.
    assert result.equity_curve[-1].equity == D("2500")
    assert benchmark.strategy_id == "buy-and-hold(X=0.5,Y=0.5)"
