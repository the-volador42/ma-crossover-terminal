"""Transform backend data into chart-friendly JSON payloads."""
from __future__ import annotations
from html import escape
from . import config
from .strategy import compute_ema

def prepare_chart_data(df, signals, live_candle=None):
    times = df.index.strftime("%Y-%m-%d %H:%M:%S").tolist()
    candles = {"x": times, "open": df["Open"].astype(float).tolist(),
        "high": df["High"].astype(float).tolist(), "low": df["Low"].astype(float).tolist(),
        "close": df["Close"].astype(float).tolist()}
    last_time = times[-1] if times else ""
    last_price = float(df["Close"].iloc[-1]) if len(df) else 0.0
    if live_candle and live_candle.get("time"):
        item = live_candle
        if candles["x"] and candles["x"][-1] == item["time"]:
            i = len(candles["x"]) - 1
            for field in ("open", "high", "low", "close"):
                candles[field][i] = float(item[field])
        else:
            candles["x"].append(item["time"])
            for field in ("open", "high", "low", "close"):
                candles[field].append(float(item[field]))
        last_time, last_price = item["time"], float(item["close"])
    ema_fast = compute_ema(df["Close"], config.FAST_EMA_PERIOD)
    ema_slow = compute_ema(df["Close"], config.SLOW_EMA_PERIOD)
    return {
        "candles": candles,
        "ema_fast": {"period": config.FAST_EMA_PERIOD, "color": config.FAST_EMA_COLOR,
                     "width": config.FAST_EMA_WIDTH, "y": [float(v) if v == v else None for v in ema_fast]},
        "ema_slow": {"period": config.SLOW_EMA_PERIOD, "color": config.SLOW_EMA_COLOR,
                     "width": config.SLOW_EMA_WIDTH, "y": [float(v) if v == v else None for v in ema_slow]},
        "signals": signals, "last_time": last_time, "last_price": last_price,
        "live_candle_time": live_candle["time"] if live_candle else None,
    }

def build_ticker_options(selected_symbol):
    items = ['<optgroup label="📈 Акции IMOEX (T-Invest API)">']
    for ticker in config.IMOEX_TICKERS:
        name = escape(config.TICKER_NAMES.get(ticker, ticker))
        selected = " selected" if ticker == selected_symbol else ""
        items.append(f'<option value="{escape(ticker)}"{selected}>{escape(ticker)} — {name}</option>')
    items.append("</optgroup>")
    is_custom = selected_symbol not in config.ALL_TICKERS
    items.append(f'<option value="__custom__"{" selected" if is_custom else ""}>🔧 Свой тикер...</option>')
    return "\n                    ".join(items)
