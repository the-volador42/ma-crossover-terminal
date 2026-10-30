"""Cache orchestration, signal notifications and API-facing state helpers."""
from __future__ import annotations
import json
from datetime import datetime
from . import config, state
from .market_data import get_days_back, get_tinkoff_candles
from .strategy import find_ma_signals

def fetch_symbol_raw(symbol, timeframe):
    df = get_tinkoff_candles(symbol, timeframe, get_days_back(timeframe))
    if df is None or df.empty:
        return None
    return {"df": df, "signals": find_ma_signals(df)}

def _signal_id(signal_type, item):
    return (signal_type, item["time"], round(float(item["price"]), 4))

def add_to_last_signals(symbol, signal_type, item):
    entry = {"symbol": symbol, "name": config.TICKER_NAMES.get(symbol, symbol),
        "type": signal_type, "price": float(item["price"]), "time": item["time"],
        "reason": item.get("reason", ""), "timestamp": datetime.now().isoformat()}
    with state.LAST_SIGNALS_LOCK:
        state.LAST_SIGNALS.insert(0, entry)
        del state.LAST_SIGNALS[config.MAX_LAST_SIGNALS:]

def notify_new_signals(symbol, timeframe, signals):
    key = (symbol, timeframe)
    current_ids = {_signal_id(item["type"], item) for item in signals}
    with state.SIGNALS_LOCK:
        seen = state.SEEN_SIGNALS.get(key, set())
        first_run = key not in state.INITIALIZED_SYMBOLS
        new_ids = current_ids - seen
        state.SEEN_SIGNALS[key] = current_ids
        state.INITIALIZED_SYMBOLS.add(key)
    if first_run or not new_ids:
        return
    for item in signals:
        if _signal_id(item["type"], item) not in new_ids:
            continue
        action = "ПОКУПКА" if item["type"] == "BUY" else "ПРОДАЖА"
        msg = f"{'🔺' if item['type']=='BUY' else '🔻'} НОВЫЙ СИГНАЛ | {symbol} [{timeframe}] | {action} | Цена: {item['price']:.2f} | Время: {item['time']} | {item.get('reason','')}"
        print(msg)
        add_to_last_signals(symbol, item["type"], item)

def broadcast_update(symbol, timeframe):
    state.STREAM_QUEUE.put(json.dumps({"type":"data_update", "symbol":symbol, "timeframe":timeframe, "timestamp":datetime.now().isoformat()}))
    with state.LAST_SIGNALS_LOCK:
        state.STREAM_QUEUE.put(json.dumps({"type":"signals_update", "signals":state.LAST_SIGNALS[:5]}))
    with state.PRICES_LOCK:
        state.STREAM_QUEUE.put(json.dumps({"type":"prices_update", "prices":dict(state.CURRENT_PRICES)}))

def broadcast_live_candle(ticker, timeframe, candle):
    state.STREAM_QUEUE.put(json.dumps({"type":"live_candle_update", "symbol":ticker, "timeframe":timeframe, "candle":candle}))

def refresh_cache_entry(symbol, timeframe):
    try:
        result = fetch_symbol_raw(symbol, timeframe)
        if result is None:
            return False
        notify_new_signals(symbol, timeframe, result["signals"])
        with state.CACHE_LOCK:
            state.CACHE[(symbol, timeframe)] = {"df":result["df"], "signals":result["signals"], "updated":datetime.now()}
        with state.LIVE_CANDLES_LOCK:
            state.LIVE_CANDLES.pop((symbol, timeframe), None)
        broadcast_update(symbol, timeframe)
        return True
    except Exception as exc:
        print(f"Ошибка обновления кэша {symbol}/{timeframe}: {exc}")
        return False

def get_cached_entry(symbol, timeframe):
    with state.CACHE_LOCK:
        entry = state.CACHE.get((symbol, timeframe))
    try:
        from .streaming import subscribe_symbol
        subscribe_symbol(symbol, timeframe)
    except Exception:
        pass
    if entry is not None:
        return entry, True
    if not refresh_cache_entry(symbol, timeframe):
        return None, False
    with state.CACHE_LOCK:
        return state.CACHE.get((symbol, timeframe)), False

def get_live_candle(ticker, timeframe):
    with state.LIVE_CANDLES_LOCK:
        item = state.LIVE_CANDLES.get((ticker, timeframe))
        return dict(item) if item else None
