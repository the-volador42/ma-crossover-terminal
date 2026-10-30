"""Application settings and instrument metadata."""
from __future__ import annotations
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

APP_NAME = "MA Crossover Terminal"
HOST = os.getenv("APP_HOST", "127.0.0.1")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))
WS_PORT = int(os.getenv("WS_PORT", "8765"))
INVEST_TOKEN = os.getenv("INVEST_TOKEN", "").strip()
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "SBER").strip().upper() or "SBER"

IMOEX_TICKERS = ['LKOH', 'SBER', 'GAZP', 'YDEX', 'T', 'TATN', 'GMKN', 'NVTK', 'PLZL', 'OZON', 'VTBR', 'SBERP', 'X5', 'ROSN', 'SNGSP', 'SNGS', 'MTSS', 'MOEX', 'HEAD', 'IRAO', 'RUAL', 'TATNP', 'CBOM', 'CHMF', 'DOMRF', 'NLMK', 'PHOR', 'AFLT', 'SVCB', 'TRNFP', 'RTKM', 'ENPG', 'MAGN', 'MDMG', 'ALRS', 'AFKS', 'FLOT', 'LENT', 'BSPB', 'VKCO', 'CNRU', 'RAGR', 'POSI', 'UGLD', 'RENI', 'MSNG']
ALL_TICKERS = IMOEX_TICKERS
TICKER_NAMES = {'SBER': 'Сбербанк', 'SBERP': 'Сбербанк (преф)', 'GAZP': 'Газпром', 'LKOH': 'Лукойл', 'YDEX': 'Яндекс (МКПАО)', 'T': 'Т-Технологии', 'NVTK': 'Новатэк', 'ROSN': 'Роснефть', 'TATN': 'Татнефть', 'TATNP': 'Татнефть (преф)', 'PLZL': 'Полюс Золото', 'ALRS': 'АЛРОСА', 'CHMF': 'Северсталь', 'NLMK': 'НЛМК', 'AFLT': 'Аэрофлот', 'VTBR': 'ВТБ', 'MOEX': 'Московская Биржа', 'GMKN': 'Норникель', 'SNGS': 'Сургутнефтегаз', 'SNGSP': 'Сургутнефтегаз (преф)', 'OZON': 'Ozon', 'VKCO': 'ВК', 'POSI': 'Positive Technologies', 'PHOR': 'ФосАгро', 'MAGN': 'ММК', 'TRNFP': 'Транснефть (преф)', 'RTKM': 'Ростелеком', 'MTSS': 'МТС', 'AFKS': 'АФК Система', 'RENI': 'Ренессанс Страхование', 'X5': 'X5 (Икс 5)', 'HEAD': 'Хэдхантер', 'CBOM': 'МКБ', 'DOMRF': 'ДОМ.РФ', 'SVCB': 'Совкомбанк', 'ENPG': 'En+ Group', 'MDMG': 'Мать и Дитя', 'BSPB': 'Банк Санкт-Петербург', 'CNRU': 'Циан', 'RAGR': 'Русагро', 'UGLD': 'ЮГК', 'MSNG': 'Мосэнерго', 'LENT': 'Лента', 'FLOT': 'Совкомфлот', 'IRAO': 'Интер РАО', 'RUAL': 'Русал'}

# Strategy parameters. They are assumptions to test, not a promise of profit.
FAST_EMA_PERIOD = 12
SLOW_EMA_PERIOD = 48
ATR_PERIOD = 14
TP_ATR_MULT = 2.4
SL_ATR_MULT = 1.8
RSI_PERIOD = 14
RSI_ENTRY_MIN = 50.0
RSI_ENTRY_MAX = 70.0
# Estimated one-way trading costs. Actual broker fees/slippage vary by instrument.
COMMISSION_PER_SIDE_PCT = float(os.getenv("COMMISSION_PER_SIDE_PCT", "0.05"))
SLIPPAGE_PER_SIDE_PCT = float(os.getenv("SLIPPAGE_PER_SIDE_PCT", "0.02"))

FAST_EMA_COLOR = "#a855f7"
SLOW_EMA_COLOR = "#f59e0b"
FAST_EMA_WIDTH = 3.0
SLOW_EMA_WIDTH = 2.0

TIMEFRAME_SPEC = {
    "1m":  ("CANDLE_INTERVAL_1_MIN", "CANDLE_INTERVAL_1_MIN", "SUBSCRIPTION_INTERVAL_ONE_MINUTE", "SUBSCRIPTION_INTERVAL_ONE_MINUTE", 1),
    "10m": ("CANDLE_INTERVAL_10_MIN", "CANDLE_INTERVAL_5_MIN", "SUBSCRIPTION_INTERVAL_10_MIN", "SUBSCRIPTION_INTERVAL_FIVE_MINUTES", 7),
    "1h":  ("CANDLE_INTERVAL_HOUR", "CANDLE_INTERVAL_HOUR", "SUBSCRIPTION_INTERVAL_ONE_HOUR", "SUBSCRIPTION_INTERVAL_ONE_HOUR", 30),
    "1d":  ("CANDLE_INTERVAL_DAY", "CANDLE_INTERVAL_DAY", "SUBSCRIPTION_INTERVAL_ONE_DAY", "SUBSCRIPTION_INTERVAL_ONE_DAY", 500),
    "1w":  ("CANDLE_INTERVAL_WEEK", "CANDLE_INTERVAL_DAY", "SUBSCRIPTION_INTERVAL_WEEK", "SUBSCRIPTION_INTERVAL_ONE_DAY", 1825),
    "1M":  ("CANDLE_INTERVAL_MONTH", "CANDLE_INTERVAL_DAY", "SUBSCRIPTION_INTERVAL_MONTH", "SUBSCRIPTION_INTERVAL_ONE_DAY", 3650),
}
PRELOAD_TIMEFRAME = "1h"
REFRESH_INTERVAL_SEC = 30 * 60
API_RATE_LIMIT = 500
API_RATE_WINDOW = 60
MAX_LAST_SIGNALS = 20
