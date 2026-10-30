import unittest
import pandas as pd
import numpy as np
from ma_terminal.strategy import compute_ema, compute_atr, compute_rsi, compute_trades, compute_trades_stats

class StrategyTests(unittest.TestCase):
    def test_ema_tracks_monotonic_series(self):
        series = pd.Series([1.0, 2.0, 3.0, 4.0])
        ema = compute_ema(series, 2)
        self.assertEqual(len(ema), 4)
        self.assertTrue(ema.is_monotonic_increasing)

    def test_atr_is_non_negative(self):
        frame = pd.DataFrame({"High":[11,12,13], "Low":[9,10,11], "Close":[10,11,12]})
        atr = compute_atr(frame, 2)
        self.assertTrue((atr.dropna() >= 0).all())

    def test_rsi_is_bounded(self):
        rsi = compute_rsi(pd.Series(np.linspace(1, 50, 80)), 14).dropna()
        self.assertTrue(((rsi >= 0) & (rsi <= 100)).all())

    def test_trade_statistics_subtract_costs(self):
        signals = [
            {"type":"BUY", "time":"2024-01-01", "price":100.0, "reason":"test"},
            {"type":"SELL", "time":"2024-01-02", "price":105.0, "reason":"test"},
        ]
        _, trades, _ = compute_trades(signals)
        self.assertEqual(len(trades), 1)
        self.assertLess(trades[0]["pnl_pct"], trades[0]["gross_pnl_pct"])
        stats = compute_trades_stats(trades)
        self.assertEqual(stats["total"], 1)

if __name__ == "__main__":
    unittest.main()
