"""HTTP API and static web UI."""
from __future__ import annotations
import json
import urllib.parse
from html import escape
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from . import config, state
from .strategy import compute_trades, compute_trades_stats
from .charts import build_ticker_options, prepare_chart_data
from .services import get_cached_entry, get_live_candle

BASE_DIR = Path(__file__).resolve().parent / "web"
MIME_TYPES = {".css":"text/css; charset=utf-8", ".js":"application/javascript; charset=utf-8", ".svg":"image/svg+xml"}

class TerminalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/update":
            return self.handle_api_update(params)
        if parsed.path == "/api/last_signals":
            with state.LAST_SIGNALS_LOCK:
                return self.send_json({"last_signals": list(state.LAST_SIGNALS[:5])})
        if parsed.path == "/api/current_prices":
            with state.PRICES_LOCK:
                return self.send_json({"prices": dict(state.CURRENT_PRICES)})
        if parsed.path.startswith("/static/"):
            return self.serve_static(parsed.path.removeprefix("/static/"))
        symbol = params.get("symbol", [config.DEFAULT_SYMBOL])[0].strip().upper()
        return self.serve_main_page(symbol or config.DEFAULT_SYMBOL)

    def handle_api_update(self, params):
        symbol = params.get("symbol", [state.CURRENT_STATE.get("symbol", "SBER")])[0].strip().upper()
        timeframe = params.get("timeframe", ["10m"])[0]
        mode = params.get("mode", ["signals"])[0]
        if not symbol:
            return self.send_json({"error":"Тикер не указан"}, 400)
        if timeframe not in config.TIMEFRAME_SPEC:
            return self.send_json({"error":"Неподдерживаемый таймфрейм"}, 400)
        if mode not in ("signals", "trading"):
            mode = "signals"
        entry, from_cache = get_cached_entry(symbol, timeframe)
        if entry is None:
            return self.send_json({"error":f"Не удалось загрузить данные для {symbol}. Проверьте токен и доступ к API."}, 503)
        df, raw_signals = entry["df"], entry["signals"]
        cache_age = max(0, int((datetime.now() - entry["updated"]).total_seconds()))
        state.CURRENT_STATE.update({"symbol":symbol, "timeframe":timeframe, "mode":mode})
        executed, trades, open_entry = compute_trades(raw_signals)
        stats = compute_trades_stats(trades, open_entry)
        chart_signals = executed if mode == "trading" else raw_signals
        chart_data = prepare_chart_data(df, chart_signals, get_live_candle(symbol, timeframe))
        with state.LAST_SIGNALS_LOCK:
            last_signals = list(state.LAST_SIGNALS[:5])
        with state.PRICES_LOCK:
            prices = dict(state.CURRENT_PRICES)
        buys = sum(s["type"] == "BUY" for s in chart_signals)
        sells = sum(s["type"] == "SELL" for s in chart_signals)
        return self.send_json({
            "success":True, "symbol":symbol, "mode":mode, "from_cache":from_cache,
            "cache_age_seconds":cache_age, "last_price":chart_data["last_price"],
            "last_time":chart_data["last_time"], "candles_count":len(df),
            "signals_count":len(chart_signals), "buys_count":buys, "sells_count":sells,
            "chart_data":chart_data, "ws_port":config.WS_PORT, "last_signals":last_signals,
            "current_prices":prices,
            "strategy_params":{"fast_period":config.FAST_EMA_PERIOD,"slow_period":config.SLOW_EMA_PERIOD,
                "atr_period":config.ATR_PERIOD,"tp_atr_mult":config.TP_ATR_MULT,"sl_atr_mult":config.SL_ATR_MULT,
                "rsi_period":config.RSI_PERIOD,"rsi_entry_min":config.RSI_ENTRY_MIN,"rsi_entry_max":config.RSI_ENTRY_MAX},
            "trades":trades,"trades_stats":stats,
        })

    def serve_main_page(self, symbol):
        template = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
        values = {
            "TICKER_NAME": escape(config.TICKER_NAMES.get(symbol, symbol)), "SYMBOL": escape(symbol),
            "TICKER_OPTIONS": build_ticker_options(symbol), "WS_PORT": str(config.WS_PORT),
            "FAST_EMA_PERIOD": str(config.FAST_EMA_PERIOD), "SLOW_EMA_PERIOD": str(config.SLOW_EMA_PERIOD),
            "ATR_PERIOD": str(config.ATR_PERIOD), "TP_ATR_MULT": str(config.TP_ATR_MULT),
        }
        for key, value in values.items():
            template = template.replace("{{" + key + "}}", value)
        return self.send_body(template.encode("utf-8"), "text/html; charset=utf-8")

    def serve_static(self, name):
        # Reject traversal paths and only serve files from the static directory.
        candidate = (BASE_DIR / "static" / name).resolve()
        static_root = (BASE_DIR / "static").resolve()
        if static_root not in candidate.parents or not candidate.is_file():
            return self.send_json({"error":"Not found"}, 404)
        return self.send_body(candidate.read_bytes(), MIME_TYPES.get(candidate.suffix, "application/octet-stream"))

    def send_json(self, payload, status=200):
        body = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")
        return self.send_body(body, "application/json; charset=utf-8", status)

    def send_body(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return

def start_http_server():
    server = ThreadingHTTPServer((config.HOST, config.HTTP_PORT), TerminalHandler)
    print(f"HTTP: http://{config.HOST}:{config.HTTP_PORT}")
    server.serve_forever()
