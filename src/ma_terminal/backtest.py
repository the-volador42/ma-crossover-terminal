"""Run an offline historical backtest from an OHLCV CSV export.

CSV columns: Date (or time), Open, High, Low, Close; Volume is optional.
The input is sorted chronologically. Metrics use estimated commission and slippage
from config.py and should not be presented as proof of future profitability.
"""
from __future__ import annotations
import argparse
import pandas as pd
from .strategy import find_ma_signals, compute_trades, compute_trades_stats

def load_csv(path: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    date_column = next((col for col in ("Date", "date", "time", "Time", "timestamp") if col in frame.columns), None)
    if date_column is None:
        raise ValueError("CSV должен содержать столбец Date, time или timestamp")
    frame[date_column] = pd.to_datetime(frame[date_column], errors="coerce", utc=True)
    frame = frame.dropna(subset=[date_column]).set_index(date_column).sort_index()
    frame.columns = [str(col).strip().title() for col in frame.columns]
    missing = {"Open", "High", "Low", "Close"} - set(frame.columns)
    if missing:
        raise ValueError(f"В CSV отсутствуют столбцы: {', '.join(sorted(missing))}")
    for col in ("Open", "High", "Low", "Close"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.dropna(subset=["Open", "High", "Low", "Close"])

def run_backtest(path: str) -> dict:
    frame = load_csv(path)
    signals = find_ma_signals(frame)
    _executed, trades, open_entry = compute_trades(signals)
    stats = compute_trades_stats(trades, open_entry)
    first_close = float(frame["Close"].iloc[0]) if len(frame) else 0.0
    last_close = float(frame["Close"].iloc[-1]) if len(frame) else 0.0
    buy_hold_pct = ((last_close / first_close) - 1.0) * 100.0 if first_close else 0.0
    stats["buy_and_hold_pct"] = buy_hold_pct
    returns = [float(trade["pnl_pct"]) for trade in trades]
    gross_wins = sum(value for value in returns if value > 0)
    gross_losses = abs(sum(value for value in returns if value < 0))
    stats["profit_factor"] = gross_wins / gross_losses if gross_losses else (float("inf") if gross_wins else 0.0)
    return {"bars":len(frame), "signals":len(signals), "stats":stats, "trades":trades}

def main():
    parser = argparse.ArgumentParser(description="Offline backtest for MA Crossover Terminal")
    parser.add_argument("csv", help="Path to OHLCV CSV")
    parser.add_argument("--show-trades", action="store_true", help="Print every closed trade")
    args = parser.parse_args()
    result = run_backtest(args.csv)
    stats = result["stats"]
    print(f"Bars: {result['bars']} | Signals: {result['signals']} | Closed trades: {stats['total']}")
    print(f"Win rate: {stats['win_rate']:.2f}% | Net compound PnL: {stats['total_pnl_pct']:.2f}%")
    print(f"Buy-and-hold over same sample: {stats['buy_and_hold_pct']:+.2f}% | Profit factor: {stats['profit_factor']:.2f}")
    print(f"Average net trade: {stats['avg_pnl_pct']:.3f}% | Average gross trade: {stats['avg_gross_pnl_pct']:.3f}%")
    print(f"Estimated round-trip costs: {stats['estimated_round_trip_cost_pct']:.3f}%")
    print("Note: this is a historical simulation, not a profitability guarantee.")
    if args.show_trades:
        for trade in result["trades"]:
            print(f"{trade['entry_time']} BUY {trade['entry_price']:.2f} -> {trade['exit_time']} SELL {trade['exit_price']:.2f} | {trade['pnl_pct']:+.3f}% net | {trade['exit_reason']}")

if __name__ == "__main__":
    main()
