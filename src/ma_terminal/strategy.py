"""Indicator calculations, deterministic signal generation and performance statistics.

Strategy: long-only EMA crossover + RSI momentum filter + ATR stop/target.
Intrabar ambiguity is resolved conservatively: if stop and target are both hit
within one candle, the stop-loss is assumed to have been hit first.
"""
from __future__ import annotations
import math
import pandas as pd

from . import config


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    if period < 1:
        raise ValueError("EMA period must be >= 1")
    return series.ewm(span=period, adjust=False).mean()


def compute_atr(df: pd.DataFrame, period: int = config.ATR_PERIOD) -> pd.Series:
    if period < 1:
        raise ValueError("ATR period must be >= 1")
    high, low = df["High"], df["Low"]
    previous_close = df["Close"].shift(1)
    true_range = pd.concat([
        high - low,
        (high - previous_close).abs(),
        (low - previous_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.ewm(alpha=1.0 / period, adjust=False).mean()


def compute_rsi(series: pd.Series, period: int = config.RSI_PERIOD) -> pd.Series:
    """Wilder-smoothed RSI with explicit handling of flat/up-only series."""
    if period < 1:
        raise ValueError("RSI period must be >= 1")
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    return rsi


def find_ma_signals(df: pd.DataFrame) -> list[dict]:
    """Generate BUY/SELL signals; call with chronologically sorted OHLC data."""
    required = {"Open", "High", "Low", "Close"}
    if df is None or df.empty or not required.issubset(df.columns):
        return []
    if len(df) < max(config.SLOW_EMA_PERIOD, config.ATR_PERIOD, config.RSI_PERIOD) + 3:
        return []

    close = df["Close"].astype(float)
    ema_fast = compute_ema(close, config.FAST_EMA_PERIOD)
    ema_slow = compute_ema(close, config.SLOW_EMA_PERIOD)
    atr = compute_atr(df, config.ATR_PERIOD)
    rsi = compute_rsi(close, config.RSI_PERIOD)
    signals: list[dict] = []
    in_position = False
    entry_price = stop_level = target_level = None
    start = max(config.SLOW_EMA_PERIOD + 1, config.RSI_PERIOD + 1, config.ATR_PERIOD + 1)

    for i in range(start, len(df)):
        values = (ema_fast.iloc[i-1], ema_slow.iloc[i-1], ema_fast.iloc[i], ema_slow.iloc[i], atr.iloc[i], rsi.iloc[i])
        if any(pd.isna(v) for v in values):
            continue
        prev_fast, prev_slow, fast, slow, atr_value, rsi_value = map(float, values)
        high = float(df["High"].iloc[i])
        low = float(df["Low"].iloc[i])
        close_price = float(close.iloc[i])
        ts = pd.Timestamp(df.index[i]).strftime("%Y-%m-%d %H:%M:%S")

        if in_position:
            # Conservative same-bar order: stop first, then target.
            if stop_level is not None and low <= stop_level:
                signals.append({"time": ts, "price": float(stop_level), "type": "SELL", "reason": "SL"})
                in_position = False
            elif target_level is not None and high >= target_level:
                signals.append({"time": ts, "price": float(target_level), "type": "SELL", "reason": "TP"})
                in_position = False
            elif prev_fast >= prev_slow and fast < slow:
                signals.append({"time": ts, "price": close_price, "type": "SELL", "reason": "cross"})
                in_position = False
            if not in_position:
                entry_price = stop_level = target_level = None
            continue  # never re-enter on the exit bar

        golden_cross = prev_fast <= prev_slow and fast > slow
        momentum_ok = config.RSI_ENTRY_MIN <= rsi_value <= config.RSI_ENTRY_MAX
        if golden_cross and momentum_ok and atr_value > 0 and close_price > slow:
            entry_price = close_price
            stop_level = entry_price - atr_value * config.SL_ATR_MULT
            target_level = entry_price + atr_value * config.TP_ATR_MULT
            signals.append({"time": ts, "price": close_price, "type": "BUY", "reason": "ema_rsi"})
            in_position = True

    return signals


def compute_trades(signals: list[dict]) -> tuple[list[dict], list[dict], dict | None]:
    """Pair sequential BUY/SELL signals and compute gross and estimated net PnL."""
    executed: list[dict] = []
    trades: list[dict] = []
    open_entry = None
    round_trip_cost_pct = 2.0 * (config.COMMISSION_PER_SIDE_PCT + config.SLIPPAGE_PER_SIDE_PCT)
    for signal in signals:
        if signal.get("type") == "BUY" and open_entry is None:
            open_entry = signal
            executed.append(signal)
        elif signal.get("type") == "SELL" and open_entry is not None:
            executed.append(signal)
            entry_price = float(open_entry["price"])
            exit_price = float(signal["price"])
            gross_pct = (exit_price - entry_price) / entry_price * 100.0 if entry_price else 0.0
            net_pct = gross_pct - round_trip_cost_pct
            trades.append({
                "entry_time": open_entry["time"], "entry_price": entry_price,
                "exit_time": signal["time"], "exit_price": exit_price,
                "exit_reason": signal.get("reason", "cross"),
                "gross_pnl_pct": float(gross_pct), "pnl_pct": float(net_pct),
                "pnl_abs": float(exit_price - entry_price),
                "estimated_cost_pct": float(round_trip_cost_pct),
            })
            open_entry = None
    return executed, trades, open_entry


def compute_trades_stats(trades: list[dict], open_entry: dict | None = None) -> dict:
    total = len(trades)
    wins = sum(1 for trade in trades if trade["pnl_pct"] > 0)
    losses = total - wins
    equity = 1.0
    for trade in trades:
        equity *= max(0.0, 1.0 + trade["pnl_pct"] / 100.0)
    return {
        "total": total, "wins": wins, "losses": losses,
        "win_rate": wins / total * 100.0 if total else 0.0,
        "total_pnl_pct": (equity - 1.0) * 100.0,
        "avg_pnl_pct": sum(t["pnl_pct"] for t in trades) / total if total else 0.0,
        "avg_gross_pnl_pct": sum(t.get("gross_pnl_pct", t["pnl_pct"]) for t in trades) / total if total else 0.0,
        "open_position": open_entry is not None,
        "open_entry_time": open_entry["time"] if open_entry else None,
        "open_entry_price": float(open_entry["price"]) if open_entry else None,
        "estimated_round_trip_cost_pct": 2.0 * (config.COMMISSION_PER_SIDE_PCT + config.SLIPPAGE_PER_SIDE_PCT),
    }
