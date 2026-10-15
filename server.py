#!/usr/bin/env python3
"""
Stock Analyzer – web tool
=========================
Local web server that lets you pick a symbol in the browser and run analyzer.py.

Usage:
    python server.py            # opens http://127.0.0.1:8765
    python server.py 9000       # custom port
"""

import json, os, re, subprocess, sys, threading, webbrowser
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE     = os.path.dirname(os.path.abspath(__file__))
ANALYZER = os.path.join(HERE, "analyzer.py")
PAGE     = os.path.join(HERE, "stock_tool.html")
WATCH    = os.path.join(HERE, "watchlist.json")
PORT     = int(sys.argv[1]) if len(sys.argv) > 1 else 8765

SYMBOL_RE    = re.compile(r"^[A-Z0-9.\-^=]{1,15}$")       # Yahoo tickers: BRK-B, ^GSPC, EURUSD=X ...
DASHBOARD_RE = re.compile(r"^[a-z0-9.\-^=]{1,15}_dashboard\.html$")
run_lock     = threading.Lock()


def list_dashboards():
    out = []
    for f in os.listdir(HERE):
        if DASHBOARD_RE.match(f):
            mtime = os.path.getmtime(os.path.join(HERE, f))
            out.append({"symbol": f[:-len("_dashboard.html")].upper(), "file": f,
                        "updated": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")})
    return sorted(out, key=lambda d: d["updated"], reverse=True)


def load_watchlist():
    try:
        with open(WATCH, encoding="utf-8") as f:
            return [s for s in json.load(f) if SYMBOL_RE.match(s)]
    except (OSError, ValueError):
        return [d["symbol"] for d in list_dashboards()]      # first use: start from existing dashboards


def save_watchlist(symbols):
    clean = list(dict.fromkeys(s.strip().upper() for s in symbols if SYMBOL_RE.match(s.strip().upper())))
    with open(WATCH, "w", encoding="utf-8") as f:
        json.dump(clean, f)
    return clean


def load_summaries(symbols):
    out = {}
    for s in symbols:
        try:
            with open(os.path.join(HERE, f"{s.lower()}_summary.json"), encoding="utf-8") as f:
                out[s] = json.load(f)
        except (OSError, ValueError):
            out[s] = None
    return out


def run_analyzer(symbol):
    env = dict(os.environ, ANALYZER_NO_BROWSER="1", PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, ANALYZER, symbol], cwd=HERE, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    log  = (p.stdout + ("\n" + p.stderr if p.stderr.strip() else "")).strip()
    file = f"{symbol.lower()}_dashboard.html"
    ok   = p.returncode == 0 and os.path.exists(os.path.join(HERE, file))
    summary = load_summaries([symbol])[symbol] if ok else None
    return {"ok": ok, "symbol": symbol, "file": file if ok else None, "summary": summary, "log": log}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj), "application/json; charset=utf-8")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            with open(PAGE, encoding="utf-8") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if url.path == "/api/list":
            return self._json(list_dashboards())
        if url.path == "/api/watchlist":
            wl = load_watchlist()
            return self._json({"symbols": wl, "summaries": load_summaries(wl)})
        if url.path.startswith("/dashboards/"):
            name = url.path[len("/dashboards/"):]
            path = os.path.join(HERE, name)
            if DASHBOARD_RE.match(name) and os.path.exists(path):
                with open(path, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
        self._send(404, "Not found", "text/plain")

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/api/watchlist":
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)
            try:
                symbols = json.loads(body or b"[]")
                assert isinstance(symbols, list) and all(isinstance(x, str) for x in symbols)
            except (ValueError, AssertionError):
                return self._json({"ok": False, "log": "Expected a JSON list of symbols"}, 400)
            wl = save_watchlist(symbols)
            return self._json({"symbols": wl, "summaries": load_summaries(wl)})
        if url.path == "/api/delete":
            symbol = (parse_qs(url.query).get("symbol", [""])[0]).strip().upper()
            if not SYMBOL_RE.match(symbol):
                return self._json({"ok": False, "log": f"Invalid symbol: {symbol!r}"}, 400)
            removed = []
            for f in (f"{symbol.lower()}_dashboard.html", f"{symbol.lower()}_summary.json"):
                path = os.path.join(HERE, f)
                if os.path.exists(path):
                    os.remove(path)
                    removed.append(f)
            print(f"  deleted: {', '.join(removed) or 'nothing'}")
            return self._json({"ok": bool(removed), "removed": removed})
        if url.path != "/api/run":
            return self._send(404, "Not found", "text/plain")
        symbol = (parse_qs(url.query).get("symbol", [""])[0]).strip().upper()
        if not SYMBOL_RE.match(symbol):
            return self._json({"ok": False, "log": f"Invalid symbol: {symbol!r}"}, 400)
        with run_lock:                      # one analysis at a time
            print(f"> Running analyzer for {symbol} ...")
            try:
                result = run_analyzer(symbol)
            except subprocess.TimeoutExpired:
                result = {"ok": False, "symbol": symbol, "log": "Timed out after 5 minutes."}
        print(f"  {'done' if result['ok'] else 'FAILED'}: {symbol}")
        self._json(result)

    def log_message(self, *args):          # keep the console quiet
        pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Stock Analyzer web tool running at {url}  (Ctrl+C to stop)")
    webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
