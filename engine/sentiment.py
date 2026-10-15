"""Sentiment marche crypto : Fear & Greed Index (alternative.me, gratuit, sans cle API).

Echelle : 0 = Fear Extreme, 100 = Greed Extreme.
Historiquement, les extremes de peur marquent des zones d'achat raisonables pour
une strategie DCA longue ; les extremes de greed des zones de prudence.
"""
import json
import urllib.request

URL = "https://api.alternative.me/fng/?limit=1"


def fear_greed(timeout=10):
    """Retourne {'valeur': int, 'label': str} ou None si la source est indisponible."""
    try:
        with urllib.request.urlopen(URL, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        d = data["data"][0]
        return {"valeur": int(d["value"]), "label": d["value_classification"]}
    except Exception:
        return None
