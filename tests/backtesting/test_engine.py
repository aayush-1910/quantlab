"""Hand-calculated toy cases for the engine. Each expected number is derived in a comment."""

import random
from decimal import Decimal

import pytest

from quantlab.backtesting.costs import CostRates, CostSchedule, CostScheduleEntry, ZeroCostModel
from quantlab.backtesting.engine import BacktestInputError, run_backtest
from quantlab.backtesting.models import OrderStatus, PriceBar, Side
from tests.backtesting.helpers import D, Scripted, bar, config, day

FREE = ZeroCostModel()

X_BARS = [bar(1, "10", "10"), bar(2, "11", "12"), bar(3, "12", "13"), bar(4, "14", "15")]


def test_buy_then_sell_matches_hand_calculation() -> None:
    # Cash 1000, no fees, no slippage. Target 100% X after session 1, 0% after session 3.
    result = run_backtest(
        {"X": X_BARS}, Scripted({1: {"X": "1"}, 3: {"X": "0"}}), FREE, config("1000")
    )

    buy, sell = result.orders
    # Session 1 close 10, equity 1000: wants floor(1000 / 10) = 100 shares.
    assert (buy.side, buy.quantity, buy.signal_date, buy.eligible_date) == (
        Side.BUY,
        100,
        day(1),
        day(2),
    )
    # Session 2 opens at 11: 1000 buys floor(1000 / 11) = 90 shares for 990. Cash 10.
    assert (buy.status, buy.filled_quantity) == (OrderStatus.PARTIALLY_FILLED, 90)
    assert buy.reasons == ("limited by available cash",)
    # Session 3 close: sell all 90, filled at session 4 open 14 for 1260.
    assert (sell.side, sell.quantity, sell.signal_date, sell.eligible_date, sell.status) == (
        Side.SELL,
        90,
        day(3),
        day(4),
        OrderStatus.FILLED,
    )
    buy_fill, sell_fill = result.fills
    assert (buy_fill.fill_date, buy_fill.price, buy_fill.value) == (day(2), D("11"), D("990.00"))
    assert (sell_fill.fill_date, sell_fill.price, sell_fill.value) == (
        day(4),
        D("14"),
        D("1260.00"),
    )
    assert buy_fill.realized_pnl is None
    assert sell_fill.realized_pnl == D("270.00")  # 1260 - 990

    # Equity: 1000 | 10 + 90*12 = 1090 | 10 + 90*13 = 1180 | 10 + 1260 = 1270.
    assert [p.equity for p in result.equity_curve] == [D("1000"), D("1090"), D("1180"), D("1270")]
    assert [p.cash for p in result.equity_curve] == [D("1000"), D("10"), D("10"), D("1270")]
    assert [p.positions_value for p in result.equity_curve] == [
        D("0"),
        D("1080"),
        D("1170"),
        D("0"),
    ]
    assert result.final_cash == D("1270")
    assert dict(result.final_positions) == {}


def test_a_close_signal_is_never_filled_at_that_close() -> None:
    result = run_backtest({"X": X_BARS}, Scripted({1: {"X": "1"}}), FREE, config("1000"))

    (fill,) = result.fills
    # The decision used session 1's close (10). The fill is at session 2's open (11).
    assert fill.fill_date > result.orders[0].signal_date
    assert fill.price == D("11") != X_BARS[0].close
    assert all(
        order.eligible_date is None or order.eligible_date > order.signal_date
        for order in result.orders
    )


def test_costs_and_slippage_match_hand_calculation() -> None:
    schedule = CostSchedule(
        "toy",
        "1",
        [
            CostScheduleEntry(
                day(1),
                None,
                CostRates(
                    brokerage_rate=D("0.001"),
                    brokerage_cap_per_order=D("20"),
                    stt_buy_rate=D("0.001"),
                    stt_sell_rate=D("0.001"),
                    exchange_rate=D("0.0001"),
                    stamp_duty_buy_rate=D("0.0002"),
                    gst_rate=D("0.18"),
                ),
                "SYNTHETIC rates invented for this test; not real charges",
            )
        ],
    )
    bars = [bar(1, "100", "100"), bar(2, "102", "105"), bar(3, "106", "110"), bar(4, "108", "108")]

    result = run_backtest(
        {"X": bars},
        Scripted({1: {"X": "0.5"}, 3: {"X": "0"}}),
        schedule,
        config("100000", slippage_bps="100"),
    )

    buy, sell = result.fills
    # Buy: floor(0.5 * 100000 / 100) = 500 shares. Open 102 + 1% = 103.02. Value 51510.00.
    #   brokerage min(51.51, 20) = 20.00 | STT 51.51 | exchange 5.151 -> 5.15
    #   stamp 10.302 -> 10.30 | GST 0.18 * (20 + 5.15) = 4.527 -> 4.53 | total 91.49
    assert (buy.quantity, buy.reference_price, buy.price, buy.value) == (
        500,
        D("102"),
        D("103.0200"),
        D("51510.00"),
    )
    assert (buy.costs.brokerage, buy.costs.stt, buy.costs.exchange_charges) == (
        D("20.00"),
        D("51.51"),
        D("5.15"),
    )
    assert (buy.costs.stamp_duty, buy.costs.gst, buy.costs.total) == (
        D("10.30"),
        D("4.53"),
        D("91.49"),
    )
    assert buy.slippage_cost == D("510.00")  # 500 * 1.02
    # Sell: open 108 - 1% = 106.92. Value 53460.00.
    #   brokerage 20.00 | STT 53.46 | exchange 5.346 -> 5.35 | no stamp duty on sells
    #   GST 0.18 * 25.35 = 4.563 -> 4.56 | total 83.37
    assert (sell.price, sell.value, sell.costs.stamp_duty, sell.costs.total) == (
        D("106.9200"),
        D("53460.00"),
        D("0"),
        D("83.37"),
    )
    assert sell.slippage_cost == D("540.00")  # 500 * 1.08
    # Cost basis 51510 + 91.49 = 51601.49. Realized 53460 - 83.37 - 51601.49 = 1775.14.
    assert sell.realized_pnl == D("1775.14")

    # Cash after buy 100000 - 51510 - 91.49 = 48398.51.
    # Equity: 100000 | 48398.51 + 500*105 | 48398.51 + 500*110 | 48398.51 + 53460 - 83.37
    assert [p.equity for p in result.equity_curve] == [
        D("100000"),
        D("100898.51"),
        D("103398.51"),
        D("101775.14"),
    ]
    last = result.equity_curve[-1]
    assert (last.cumulative_fees, last.cumulative_slippage) == (D("174.86"), D("1050.00"))
    # Adding fees and slippage back gives the frictionless result: 500 * (108 - 102) = 3000.
    assert last.equity + last.cumulative_fees + last.cumulative_slippage == D("103000.00")


def test_volume_limit_gives_a_partial_fill_and_the_rest_is_cancelled() -> None:
    bars = [bar(1, "10", "10"), bar(2, "10", "10", volume=1000), bar(3, "10", "10")]

    result = run_backtest(
        {"X": bars}, Scripted({1: {"X": "1"}}), FREE, config("10000", participation="0.1")
    )

    (order,) = result.orders
    # Wants 1000 shares; 10% of the 1000-share session is 100.
    assert (order.quantity, order.filled_quantity, order.status) == (
        1000,
        100,
        OrderStatus.PARTIALLY_FILLED,
    )
    assert "session volume" in order.reasons[0]
    assert len(result.fills) == 1  # the unfilled 900 are not carried to session 3
    assert result.final_positions["X"].quantity == 100


def test_zero_volume_session_rejects_the_order() -> None:
    bars = [bar(1, "10", "10"), bar(2, "10", "10", volume=0)]

    result = run_backtest(
        {"X": bars}, Scripted({1: {"X": "1"}}), FREE, config("1000", participation="0.5")
    )

    assert result.orders[0].status is OrderStatus.REJECTED
    assert result.fills == ()
    assert result.final_cash == D("1000")


def test_order_for_an_instrument_with_no_bar_on_the_eligible_session_is_rejected() -> None:
    x = [bar(1, "10", "10"), bar(3, "10", "10")]  # X has no bar in session 2
    y = [bar(1, "5", "5"), bar(2, "5", "5"), bar(3, "5", "5")]

    result = run_backtest({"X": x, "Y": y}, Scripted({1: {"X": "1"}}), FREE, config("1000"))

    (order,) = result.orders
    assert (order.status, order.eligible_date) == (OrderStatus.REJECTED, day(2))
    assert order.reasons == ("no bar on the eligible session",)
    assert result.fills == ()


def test_order_decided_on_the_last_session_is_recorded_as_unfilled() -> None:
    result = run_backtest({"X": X_BARS}, Scripted({4: {"X": "1"}}), FREE, config("1000"))

    (order,) = result.orders
    assert order.status is OrderStatus.UNFILLED_NO_LATER_SESSION
    assert order.eligible_date is None
    assert result.final_cash == D("1000")


def test_sells_fill_before_buys_so_proceeds_fund_the_rotation() -> None:
    x = [bar(n, "10", "10") for n in range(1, 5)]
    y = [bar(n, "20", "20") for n in range(1, 5)]

    result = run_backtest(
        {"X": x, "Y": y},
        Scripted({1: {"X": "1"}, 2: {"X": "0", "Y": "1"}}),
        FREE,
        config("1000"),
    )

    assert [(f.fill_date, f.instrument_id, f.side, f.quantity) for f in result.fills] == [
        (day(2), "X", Side.BUY, 100),
        (day(3), "X", Side.SELL, 100),
        (day(3), "Y", Side.BUY, 50),  # only affordable because the sell came first
    ]
    assert all(order.status is OrderStatus.FILLED for order in result.orders)
    assert result.final_cash == D("0")


def test_a_held_instrument_without_a_bar_is_valued_at_its_last_close_and_flagged() -> None:
    x = [bar(1, "10", "10"), bar(2, "10", "12"), bar(4, "12", "9")]  # no session 3
    y = [bar(n, "5", "5") for n in range(1, 5)]

    result = run_backtest({"X": x, "Y": y}, Scripted({1: {"X": "1"}}), FREE, config("1000"))

    assert [p.equity for p in result.equity_curve] == [D("1000"), D("1200"), D("1200"), D("900")]
    assert [p.stale_valuations for p in result.equity_curve] == [0, 0, 1, 0]


def test_target_without_a_close_on_the_signal_date_is_rejected_not_guessed() -> None:
    x = [bar(1, "10", "10"), bar(3, "10", "10")]
    y = [bar(n, "5", "5") for n in range(1, 4)]

    result = run_backtest({"X": x, "Y": y}, Scripted({2: {"X": "1"}}), FREE, config("1000"))

    (order,) = result.orders
    assert order.status is OrderStatus.REJECTED
    assert order.reasons == ("no close on the signal date to size the order",)


def test_strategy_never_sees_a_bar_after_the_decision_date() -> None:
    strategy = Scripted({})

    run_backtest({"X": X_BARS}, strategy, FREE, config())

    assert [decision for decision, _ in strategy.seen] == [day(1), day(2), day(3), day(4)]
    assert all(latest == decision for decision, latest in strategy.seen)


def test_changing_future_bars_does_not_change_the_past() -> None:
    script = {1: {"X": "1"}, 2: {"X": "0.5"}, 3: {"X": "0"}}
    altered = [*X_BARS[:3], PriceBar(day(4), D("999"), D("999"), D("1"), D("1"), 5)]

    base = run_backtest({"X": X_BARS}, Scripted(script), FREE, config("1000"))
    changed = run_backtest({"X": altered}, Scripted(script), FREE, config("1000"))

    assert base.equity_curve[:3] == changed.equity_curve[:3]
    assert [f for f in base.fills if f.fill_date <= day(3)] == [
        f for f in changed.fills if f.fill_date <= day(3)
    ]
    assert [(o.signal_date, o.side, o.quantity) for o in base.orders] == [
        (o.signal_date, o.side, o.quantity) for o in changed.orders
    ]


class _RandomWeights:
    strategy_id = "random-weights"

    def __init__(self, seed: int, instruments: list[str]) -> None:
        self._rng = random.Random(seed)  # noqa: S311 - test data, not security
        self._instruments = instruments

    def decide(self, context: object) -> dict[str, Decimal] | None:
        if self._rng.random() < 0.3:
            return None
        share = Decimal(1) / Decimal(len(self._instruments))
        return {
            instrument: (share * Decimal(self._rng.randint(0, 100)) / 100)
            for instrument in self._instruments
        }


def _random_bars(seed: int) -> dict[str, list[PriceBar]]:
    rng = random.Random(seed)  # noqa: S311 - test data, not security
    bars: dict[str, list[PriceBar]] = {}
    for name in ("A", "B", "C"):
        price = Decimal(rng.randint(20, 500))
        series = []
        for n in range(1, 61):
            if rng.random() < 0.1:
                continue  # a missing bar
            open_ = (price * Decimal(rng.randint(95, 105)) / 100).quantize(Decimal("0.05"))
            price = (open_ * Decimal(rng.randint(95, 105)) / 100).quantize(Decimal("0.05"))
            series.append(
                PriceBar(
                    day(n), open_, max(open_, price), min(open_, price), price, rng.randint(0, 5000)
                )
            )
        bars[name] = series
    return bars


RATES = CostSchedule(
    "toy",
    "1",
    [
        CostScheduleEntry(
            day(1),
            None,
            CostRates(brokerage_rate=D("0.0005"), stt_sell_rate=D("0.001"), gst_rate=D("0.18")),
            "SYNTHETIC rates invented for this test; not real charges",
        )
    ],
)


@pytest.mark.parametrize("seed", range(25))
def test_cash_and_positions_reconcile_with_fills_on_random_runs(seed: int) -> None:
    bars = _random_bars(seed)
    setup = config("50000", slippage_bps="7", participation="0.25")

    result = run_backtest(bars, _RandomWeights(seed, list(bars)), RATES, setup)

    cash = setup.initial_cash
    held: dict[str, int] = {}
    for fill in result.fills:
        signed = fill.quantity if fill.side is Side.BUY else -fill.quantity
        held[fill.instrument_id] = held.get(fill.instrument_id, 0) + signed
        cash += (
            -fill.value - fill.costs.total
            if fill.side is Side.BUY
            else fill.value - fill.costs.total
        )
        assert cash >= 0  # never spends money it does not have
        assert held[fill.instrument_id] >= 0  # never short
    assert cash == result.final_cash
    assert {k: v for k, v in held.items() if v} == {
        k: p.quantity for k, p in result.final_positions.items()
    }
    for order in result.orders:
        fills = [f for f in result.fills if f.order_id == order.order_id]
        assert sum(f.quantity for f in fills) == order.filled_quantity <= order.quantity
        assert all(f.fill_date == order.eligible_date for f in fills)
        assert order.eligible_date is None or order.eligible_date > order.signal_date
    last = result.equity_curve[-1]
    assert last.cumulative_fees == sum((f.costs.total for f in result.fills), Decimal(0))
    assert all(p.equity == p.cash + p.positions_value for p in result.equity_curve)


@pytest.mark.parametrize("seed", [0, 7])
def test_identical_inputs_give_identical_results(seed: int) -> None:
    bars = _random_bars(seed)
    setup = config("50000", slippage_bps="7", participation="0.25")

    first = run_backtest(bars, _RandomWeights(seed, list(bars)), RATES, setup)
    second = run_backtest(bars, _RandomWeights(seed, list(bars)), RATES, setup)

    assert first.equity_curve == second.equity_curve
    assert first.orders == second.orders
    assert first.fills == second.fills


@pytest.mark.parametrize(
    ("targets", "message"),
    [
        ({"X": "0.7", "Y": "0.4"}, "above 1"),
        ({"X": "-0.1"}, "invalid"),
        ({"Z": "0.5"}, "unknown instrument"),
    ],
)
def test_invalid_targets_stop_the_run(targets: dict[str, str], message: str) -> None:
    y = [bar(n, "5", "5") for n in range(1, 5)]

    with pytest.raises(BacktestInputError, match=message):
        run_backtest({"X": X_BARS, "Y": y}, Scripted({1: targets}), FREE, config())


def test_invalid_bars_and_configuration_are_rejected() -> None:
    with pytest.raises(BacktestInputError, match="increasing date order"):
        run_backtest({"X": [X_BARS[1], X_BARS[0]]}, Scripted({}), FREE, config())
    with pytest.raises(BacktestInputError, match="no bars"):
        run_backtest({"X": []}, Scripted({}), FREE, config())
    with pytest.raises(BacktestInputError, match="invalid price"):
        run_backtest({"X": [bar(1, "0", "10")]}, Scripted({}), FREE, config())
    with pytest.raises(BacktestInputError, match="initial_cash"):
        config("0")
    with pytest.raises(BacktestInputError, match="max_participation"):
        config(participation="1.5")
    with pytest.raises(BacktestInputError, match="slippage_bps"):
        config(slippage_bps="-1")
