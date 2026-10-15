"""Client eToro Public API (https://public-api.etoro.com).

Auth : en-têtes x-api-key + x-user-key (compte eToro vérifié,
Paramètres > Trading > Gestion des clés API — docs : https://api-portal.etoro.com).
La user key n'est affichée qu'une fois à la création ; à conserver dans .env.

Ordres démo : POST /api/v2/trading/execution/demo/orders (faux argent)
Ordres réels : POST /api/v2/trading/execution/orders
Limites : ~60 req/min par défaut, 20 écritures d'ordres / 60 s.
"""
import json
import time
import urllib.error
import urllib.request
import uuid


class ErreurEtoro(Exception):
    """Erreur d'appel à l'API eToro (HTTP, clés manquantes, ordre rejeté...)."""


def _headers(api_key, user_key):
    return {
        "x-api-key": api_key,
        "x-user-key": user_key,
        "x-request-id": str(uuid.uuid4()),  # idempotence, exigé par l'API
        "Content-Type": "application/json",
        "Accept": "application/json",
        # Cloudflare (Error 1010) bloque l'User-Agent par defaut de Python urllib :
        # signature navigateur requise meme pour un client API legitime.
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/129.0.0.0 Safari/537.36"),
    }


BASE_URL = "https://public-api.etoro.com"


def set_base(url):
    """Permet de redéfinir la base (tests ou proxy) si nécessaire."""
    global BASE_URL
    BASE_URL = url.rstrip("/")


def _appel(methode, chemin, api_key, user_key, corps=None, timeout=15):
    if not api_key or not user_key:
        raise ErreurEtoro("Clés eToro manquantes : renseigner ETORO_API_KEY et "
                          "ETORO_USER_KEY dans .env (Paramètres > Trading > Gestion des clés API)")
    url = BASE_URL + chemin
    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    req = urllib.request.Request(url, data=donnees, headers=_headers(api_key, user_key),
                                 method=methode)
    essais = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            corps_err = e.read().decode("utf-8", "replace")
            if e.code == 429 and essais < 3:  # backoff exponentiel conseillé par les docs
                essais += 1
                time.sleep(2 ** essais)
                continue
            raise ErreurEtoro(f"HTTP {e.code} sur {chemin} : {corps_err[:300]}") from None
        except urllib.error.URLError as e:
            raise ErreurEtoro(f"Réseau indisponible ({e.reason})") from None


def resoudre_instrument(symbole, api_key, user_key):
    """Résout un symbole (BTC, ETH...) en instrumentId numérique eToro."""
    rep = _appel("GET", f"/api/v1/market-data/search?internalSymbolFull={symbole}",
                 api_key, user_key)
    for item in rep.get("items", []):
        if str(item.get("internalSymbolFull", "")).upper() == symbole.upper():
            return int(item["instrumentId"])
    raise ErreurEtoro(f"Instrument {symbole} introuvable sur eToro")


def acheter_marche(instrument_id, montant_usd, api_key, user_key, demo=True):
    """Ordre au marché ACHAT, sans levier (leverage 1), montant en USD."""
    chemin = ("/api/v2/trading/execution/demo/orders" if demo
              else "/api/v2/trading/execution/orders")
    corps = {
        "action": "open",
        "transaction": "buy",
        "instrumentId": int(instrument_id),
        "orderType": "mkt",
        "leverage": 1,
        "amount": round(float(montant_usd), 2),
        "orderCurrency": "usd",
    }
    return _appel("POST", chemin, api_key, user_key, corps)


def attendre_execution(order_id, api_key, user_key, essais=6, pause=2.0):
    """Interroge orders:lookup — statut 3/5 = exécuté, 4/10 = rejeté, sinon en cours."""
    for _ in range(essais):
        rep = _appel("GET", f"/api/v2/trading/info/orders:lookup?orderId={order_id}",
                     api_key, user_key)
        st = rep.get("status")
        if st in (3, 5):
            return rep
        if st in (4, 10):
            raise ErreurEtoro(f"Ordre {order_id} rejeté par eToro : {rep}")
        time.sleep(pause)
    return {"status": "en_cours", "orderId": order_id,
            "detail": "délai dépassé — vérifier la position sur eToro"}
