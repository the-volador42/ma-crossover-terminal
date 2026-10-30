"""Application entry point."""
from __future__ import annotations
import threading
import time
import webbrowser
from . import config
from .market_data import load_instruments
from .streaming import run_websocket_server, queue_flush_worker, tinkoff_stream_worker, update_queue_worker, preload_worker
from .web_server import start_http_server

def main():
    if not config.INVEST_TOKEN:
        raise SystemExit("Не задан INVEST_TOKEN. Скопируйте .env.example в .env и добавьте токен.")
    # No interactive ticker menu: use DEFAULT_SYMBOL from .env (SBER by default).
    symbol = config.DEFAULT_SYMBOL
    print(f"Выбран тикер: {symbol}")
    load_instruments()
    workers = [
        (run_websocket_server, (config.WS_PORT,)),
        (queue_flush_worker, ()),
        (tinkoff_stream_worker, ()),
        (update_queue_worker, ()),
        (preload_worker, ()),
    ]
    for target, args in workers:
        threading.Thread(target=target, args=args, daemon=True, name=target.__name__).start()
    threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(f"http://{config.HOST}:{config.HTTP_PORT}")), daemon=True).start()
    start_http_server()

if __name__ == "__main__":
    main()
