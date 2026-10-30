"""T-Invest SDK adapter for instrument discovery and historical candles."""
from __future__ import annotations
import time
from datetime import datetime, timedelta, timezone
import pandas as pd
import pytz

from . import config, state

try:
    from t_tech.invest import Client, CandleInterval, CandleInstrument, SubscriptionInterval
except ImportError:  # Enables unit tests and offline backtests without the broker SDK.
    Client = CandleInterval = CandleInstrument = SubscriptionInterval = None

MSK_TZ = pytz.timezone("Europe/Moscow")

def _require_sdk():
    if Client is None:
        raise RuntimeError("Не установлен SDK T-Invest. Установите пакет по инструкции в README.md")
    if not config.INVEST_TOKEN:
        raise RuntimeError("Не задан INVEST_TOKEN в .env / переменных окружения")

def rate_limit_wait():
    with state.REQUEST_LOCK:
        now = time.time()
        while state.REQUEST_TIMESTAMPS and state.REQUEST_TIMESTAMPS[0] < now - config.API_RATE_WINDOW:
            state.REQUEST_TIMESTAMPS.popleft()
        if len(state.REQUEST_TIMESTAMPS) >= config.API_RATE_LIMIT:
            delay = max(0.0, state.REQUEST_TIMESTAMPS[0] - (now - config.API_RATE_WINDOW))
            if delay:
                time.sleep(delay)
                now = time.time()
                while state.REQUEST_TIMESTAMPS and state.REQUEST_TIMESTAMPS[0] < now - config.API_RATE_WINDOW:
                    state.REQUEST_TIMESTAMPS.popleft()
        state.REQUEST_TIMESTAMPS.append(time.time())

def resolve_enum(enum_cls, name, fallback):
    value = getattr(enum_cls, name, None)
    if value is None:
        value = getattr(enum_cls, fallback)
    return value

def get_timeframe_map():
    _require_sdk()
    result = {}
    for tf, (c_name, c_fallback, s_name, s_fallback, _days) in config.TIMEFRAME_SPEC.items():
        result[tf] = (
            resolve_enum(CandleInterval, c_name, c_fallback),
            resolve_enum(SubscriptionInterval, s_name, s_fallback),
        )
    return result

def get_days_back(timeframe: str) -> int:
    return config.TIMEFRAME_SPEC.get(timeframe, config.TIMEFRAME_SPEC["10m"])[4]

def q_to_float(value) -> float:
    if value is None:
        return 0.0
    return float(value.units + value.nano / 1e9)

def load_instruments() -> None:
    _require_sdk()
    rate_limit_wait()
    try:
        with Client(config.INVEST_TOKEN) as client:
            shares = client.instruments.shares().instruments
        mapping = {share.ticker: share.figi for share in shares if share.currency == "rub" and share.figi}
        with state.FIGI_LOCK:
            state.FIGI_CACHE.update(mapping)
        print(f"Загружено инструментов: {len(mapping)}")
    except Exception as exc:
        print(f"Не удалось загрузить список инструментов: {exc}")

def get_figi(ticker: str):
    with state.FIGI_LOCK:
        figi = state.FIGI_CACHE.get(ticker.upper())
    if figi:
        with state.FIGI_LOCK:
            state.FIGI_TO_TICKER[figi] = ticker.upper()
        return figi
    if not config.INVEST_TOKEN or Client is None:
        return None
    try:
        rate_limit_wait()
        with Client(config.INVEST_TOKEN) as client:
            response = client.instruments.find_instrument(query=ticker)
        for item in response.instruments:
            if item.ticker.upper() == ticker.upper() and item.api_trade_available_flag:
                with state.FIGI_LOCK:
                    state.FIGI_CACHE[ticker.upper()] = item.figi
                    state.FIGI_TO_TICKER[item.figi] = ticker.upper()
                return item.figi
    except Exception as exc:
        print(f"Не удалось найти FIGI для {ticker}: {exc}")
    return None

def get_tinkoff_candles(ticker: str, timeframe: str, days_back: int | None = None):
    _require_sdk()
    figi = get_figi(ticker)
    if not figi:
        print(f"Не найден FIGI для {ticker}")
        return None
    tf_map = get_timeframe_map()
    candle_interval, _ = tf_map.get(timeframe, tf_map["10m"])
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back or get_days_back(timeframe))
    rows = []
    try:
        rate_limit_wait()
        with Client(config.INVEST_TOKEN) as client:
            candles = client.get_all_candles(figi=figi, from_=start, to=end, interval=candle_interval)
            for candle in candles:
                if not getattr(candle, "is_complete", True):
                    continue
                rows.append({"time": candle.time, "Open": q_to_float(candle.open),
                    "High": q_to_float(candle.high), "Low": q_to_float(candle.low),
                    "Close": q_to_float(candle.close), "Volume": float(candle.volume)})
    except Exception as exc:
        print(f"Ошибка загрузки свечей {ticker}/{timeframe}: {exc}")
        return None
    if not rows:
        print(f"Нет свечей для {ticker} [{timeframe}]")
        return None
    frame = pd.DataFrame(rows)
    frame["time"] = pd.to_datetime(frame["time"], utc=True).dt.tz_convert(MSK_TZ)
    frame.set_index("time", inplace=True)
    frame.sort_index(inplace=True)
    return frame[~frame.index.duplicated(keep="first")]
