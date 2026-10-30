"""Broker market-data stream, reconnect handling, and browser WebSocket fan-out."""
from __future__ import annotations
import asyncio, json, queue, time
from datetime import datetime, timezone
import websockets
from . import config, state
from .market_data import Client, CandleInstrument, get_figi, get_timeframe_map, q_to_float, MSK_TZ
from .services import broadcast_live_candle, refresh_cache_entry

def subscribe_symbol(ticker, timeframe):
    if timeframe not in config.TIMEFRAME_SPEC:
        return
    figi = get_figi(ticker)
    if not figi:
        return
    key = (figi, timeframe)
    with state.SUB_LOCK:
        if key in state.ACTIVE_SUBSCRIPTIONS:
            return
        state.ACTIVE_SUBSCRIPTIONS.add(key)
    with state.STREAM_MANAGER_LOCK:
        manager = state.STREAM_MANAGER
    if manager is None:
        return
    try:
        _, sub_interval = get_timeframe_map()[timeframe]
        manager.candles.subscribe([CandleInstrument(figi=figi, interval=sub_interval)])
        print(f"Подписка на стрим: {ticker} [{timeframe}]")
    except Exception as exc:
        print(f"Не удалось подписаться на {ticker}/{timeframe}: {exc}")

def resubscribe_all(manager):
    with state.SUB_LOCK:
        subscriptions = list(state.ACTIVE_SUBSCRIPTIONS)
    tf_map = get_timeframe_map()
    instruments = [CandleInstrument(figi=figi, interval=tf_map.get(tf, tf_map["10m"])[1]) for figi, tf in subscriptions if tf in tf_map]
    if instruments:
        manager.candles.subscribe(instruments)


def handle_incoming_candle(candle):
    with state.FIGI_LOCK:
        ticker = state.FIGI_TO_TICKER.get(candle.figi)
    if not ticker:
        return
    interval = candle.interval
    try:
        tf_map = get_timeframe_map()
        timeframe = next((tf for tf, (_c, sub) in tf_map.items() if sub == interval), None)
    except Exception:
        return
    if timeframe is None:
        return
    values = {"open":q_to_float(candle.open), "high":q_to_float(candle.high), "low":q_to_float(candle.low), "close":q_to_float(candle.close)}
    with state.PRICES_LOCK:
        state.CURRENT_PRICES[ticker] = values["close"]
    timestamp = candle.time
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    time_str = timestamp.astimezone(MSK_TZ).strftime("%Y-%m-%d %H:%M:%S")
    live_entry = {"time":time_str, **values}
    with state.LIVE_CANDLES_LOCK:
        state.LIVE_CANDLES[(ticker, timeframe)] = live_entry
    if getattr(candle, "is_complete", True):
        state.UPDATE_QUEUE.put((ticker, timeframe))
    broadcast_live_candle(ticker, timeframe, live_entry)

def tinkoff_stream_worker():
    if not config.INVEST_TOKEN or Client is None:
        print("T-Invest stream disabled: set INVEST_TOKEN and install the official SDK.")
        return
    while True:
        try:
            print("Подключение к T-Invest market-data stream...")
            with Client(config.INVEST_TOKEN) as client:
                manager = client.create_market_data_stream()
                with state.STREAM_MANAGER_LOCK:
                    state.STREAM_MANAGER = manager
                resubscribe_all(manager)
                for item in manager:
                    if item.candle is not None and item.candle.figi:
                        handle_incoming_candle(item.candle)
        except Exception as exc:
            print(f"Стрим отключился: {exc}. Повтор через 5 секунд...")
        finally:
            with state.STREAM_MANAGER_LOCK:
                state.STREAM_MANAGER = None
            time.sleep(5)


def queue_flush_worker():
    while state.WS_EVENT_LOOP is None:
        time.sleep(0.1)
    while True:
        message = state.STREAM_QUEUE.get()
        with state.WS_LOCK:
            clients = list(state.WS_CLIENTS)
        for client in clients:
            try:
                asyncio.run_coroutine_threadsafe(client.send(message), state.WS_EVENT_LOOP)
            except Exception:
                with state.WS_LOCK:
                    state.WS_CLIENTS.discard(client)

def update_queue_worker():
    print("Воркер обновления свечей запущен")
    while True:
        try:
            ticker, timeframe = state.UPDATE_QUEUE.get(timeout=1)
            key = (ticker, timeframe)
            with state.CACHE_LOCK:
                entry = state.CACHE.get(key)
                if entry and (datetime.now() - entry["updated"]).total_seconds() < 30:
                    continue
            refresh_cache_entry(ticker, timeframe)
            time.sleep(2)
        except queue.Empty:
            continue
        except Exception as exc:
            print(f"Ошибка update worker: {exc}")
            time.sleep(5)

async def websocket_handler(websocket, path=None):
    with state.WS_LOCK:
        state.WS_CLIENTS.add(websocket)
    try:
        await websocket.send(json.dumps({"type":"connected", "message":"Подключено к стримингу"}))
        with state.LAST_SIGNALS_LOCK:
            last_signals = list(state.LAST_SIGNALS[:5])
        await websocket.send(json.dumps({"type":"signals_update", "signals":last_signals}))
        with state.PRICES_LOCK:
            prices = dict(state.CURRENT_PRICES)
        await websocket.send(json.dumps({"type":"prices_update", "prices":prices}))
        async for message in websocket:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"type":"error", "message":"Неверный формат JSON"}))
                continue
            if data.get("type") == "subscribe":
                symbol = str(data.get("symbol", "")).strip().upper()
                timeframe = str(data.get("timeframe", "10m"))
                if symbol and timeframe in config.TIMEFRAME_SPEC:
                    await asyncio.get_running_loop().run_in_executor(None, _prime_symbol, symbol, timeframe)
                    await websocket.send(json.dumps({"type":"subscribed", "symbol":symbol, "timeframe":timeframe}))
                    with state.LIVE_CANDLES_LOCK:
                        live = state.LIVE_CANDLES.get((symbol, timeframe))
                    if live:
                        await websocket.send(json.dumps({"type":"live_candle_update", "symbol":symbol, "timeframe":timeframe, "candle":live}))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        with state.WS_LOCK:
            state.WS_CLIENTS.discard(websocket)

def _prime_symbol(symbol, timeframe):
    from .services import get_cached_entry
    get_cached_entry(symbol, timeframe)

async def start_websocket_server(port: int | None = None):
    port = port or config.WS_PORT
    print(f"WebSocket: ws://{config.HOST}:{port}")
    async with websockets.serve(websocket_handler, config.HOST, port):
        await asyncio.Future()

def run_websocket_server(port: int | None = None):
    state.WS_EVENT_LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(state.WS_EVENT_LOOP)
    state.WS_EVENT_LOOP.run_until_complete(start_websocket_server(port))

def preload_worker():
    if not config.INVEST_TOKEN:
        print("Предзагрузка отключена: INVEST_TOKEN не задан.")
        return
    from .services import refresh_cache_entry
    while True:
        for idx, ticker in enumerate(config.ALL_TICKERS):
            refresh_cache_entry(ticker, config.PRELOAD_TIMEFRAME)
            if idx < len(config.ALL_TICKERS) - 1:
                time.sleep(6)
        time.sleep(config.REFRESH_INTERVAL_SEC)
