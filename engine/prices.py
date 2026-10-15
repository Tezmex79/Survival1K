"""Prix reels via l'API publique Binance (CCXT) - aucune cle API requise."""
import time

import ccxt


def make_exchange(cfg, api_key=None, secret=None):
    kwargs = {}
    if api_key and secret:
        kwargs.update({"apiKey": api_key, "secret": secret})
    ex = getattr(ccxt, cfg["exchange"]["id"])(**kwargs)
    ex.enableRateLimit = True  # natif dans ccxt >= 4.5, plus un argument de constructeur
    return ex


def _retry(fn, attempts=3):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def get_prices(exchange, paires):
    """Prix spot actuels {actif: prix_eur} pour les paires du config."""
    out = {}
    for asset, symbol in paires.items():
        ticker = _retry(lambda: exchange.fetch_ticker(symbol))
        out[asset] = float(ticker["last"])
    return out


def get_daily_closes(exchange, symbol, days):
    """Closes quotidiennes [(timestamp_ms, close)] sur `days` jours, avec pagination."""
    ms_day = 86_400_000
    since = exchange.milliseconds() - days * ms_day
    rows = []
    while True:
        batch = _retry(lambda: exchange.fetch_ohlcv(symbol, "1d", since=since, limit=1000))
        if not batch:
            break
        rows.extend(batch)
        since = batch[-1][0] + ms_day
        if len(batch) < 1000 or since > exchange.milliseconds():
            break
    uniques = {r[0]: r[4] for r in rows}  # dedoublonne sur le timestamp
    return sorted((ts, close) for ts, close in uniques.items())


def change_pct(closes, window_days):
    """Variation en % sur `window_days` glissants, a partir des closes quotidiennes."""
    if len(closes) < window_days + 1:
        raise ValueError(f"Historique insuffisant: {len(closes)} closes, {window_days + 1} requis")
    past = closes[-(window_days + 1)][1]
    last = closes[-1][1]
    return (last / past - 1) * 100
