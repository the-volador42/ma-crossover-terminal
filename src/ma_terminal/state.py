"""Shared runtime state. Mutable values are centralized to make ownership visible."""
from __future__ import annotations
import asyncio
import queue
import threading
from collections import deque
from datetime import datetime

REQUEST_TIMESTAMPS = deque(maxlen=500)
REQUEST_LOCK = threading.Lock()
CACHE: dict = {}
CACHE_LOCK = threading.Lock()
SEEN_SIGNALS: dict = {}
INITIALIZED_SYMBOLS: set = set()
SIGNALS_LOCK = threading.Lock()
WS_CLIENTS: set = set()
WS_LOCK = threading.Lock()
WS_EVENT_LOOP: asyncio.AbstractEventLoop | None = None
STREAM_QUEUE: queue.Queue = queue.Queue()
FIGI_CACHE: dict = {}
FIGI_TO_TICKER: dict = {}
FIGI_LOCK = threading.Lock()
ACTIVE_SUBSCRIPTIONS: set = set()
SUB_LOCK = threading.Lock()
STREAM_MANAGER = None
STREAM_MANAGER_LOCK = threading.Lock()
LAST_SIGNALS: list[dict] = []
LAST_SIGNALS_LOCK = threading.Lock()
CURRENT_PRICES: dict = {}
PRICES_LOCK = threading.Lock()
LIVE_CANDLES: dict = {}
LIVE_CANDLES_LOCK = threading.Lock()
UPDATE_QUEUE: queue.Queue = queue.Queue()
CURRENT_STATE = {"symbol": "SBER", "timeframe": "10m", "mode": "signals"}
