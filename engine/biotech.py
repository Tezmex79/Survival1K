"""Sleeve actions biomedicales : lignes evenementielles FDA/EMA en portefeuille papier.

Donnees de cours : Stooq (gratuit, sans cle) — actions US au format 'xxxx.us'.
Les montants sont investis en EUR puis convertis en USD au taux du jour
(proxy EUR/USDT, cf. run_dca.taux_usd_par_eur) car les titres cotent en USD
et les ordres eToro passent en USD.
"""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
FICHIER = DATA / "biotech.json"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbole}?interval=1d&range=5d"
# Stooq (gratuit aussi) a active un challenge anti-bot JavaScript en oct. 2026 ->
# abandonne. L'endpoint chart de Yahoo Finance, non officiel mais stable depuis
# des annees, fournit le dernier prix sans cle (User-Agent navigateur requis).


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cours_usd(symboles):
    """Dernier prix Yahoo Finance : {'bbio': {'close': x, 'date': y}} (USD).

    Symboles US simples ('BBIO'), une requete par ticker, bascule query1/query2
    en cas d'echec. Le prix est le regularMarketPrice (quasi temps reel).
    """
    out = {}
    for s in symboles:
        s = s.strip().upper()
        if not s:
            continue
        for hote in ("query1", "query2"):
            url = YAHOO_CHART.format(symbole=s).replace("query1", hote, 1)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    rep = json.loads(r.read().decode("utf-8"))
                meta = rep["chart"]["result"][0]["meta"]
                prix = float(meta["regularMarketPrice"])
                ts = int(meta.get("regularMarketTime") or 0)
                date = (datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                        if ts else "")
                out[s.lower()] = {"close": prix, "date": date}
                break
            except Exception:
                continue
    return out


def _defaut(budget_eur):
    return {"budget_eur": float(budget_eur), "positions": [], "cloturees": [], "journal": []}


def charger(cfg):
    DATA.mkdir(exist_ok=True)
    if FICHIER.exists():
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    etat = _defaut(cfg["allocation"].get("biotech_eur", 0))
    sauver(etat)
    return etat


def sauver(etat):
    DATA.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(etat, indent=2, ensure_ascii=False), encoding="utf-8")


def cash_disponible(etat):
    investi = sum(p["eur_investis"] for p in etat["positions"])
    return round(etat["budget_eur"] - investi, 2)


def acheter(etat, ticker, eur, taux_usd, prix_usd, catalyseur, date_catalyseur, nom=""):
    """Achat papier : EUR -> USD au taux du jour, quantite = montant hors frais / prix."""
    if any(p["ticker"].lower() == ticker.lower() for p in etat["positions"]):
        raise ValueError(f"{ticker} est deja en portefeuille")
    montant_usd = eur * taux_usd
    qty = round(montant_usd / prix_usd, 4)
    p = {
        "ticker": ticker.upper(), "nom": nom, "date_achat": now_iso(),
        "eur_investis": round(eur, 2), "taux_usd_entree": round(taux_usd, 4),
        "prix_entree_usd": prix_usd, "qty": qty,
        "catalyseur": catalyseur, "date_catalyseur": date_catalyseur,
        "statut": "ouverte",
    }
    etat["positions"].append(p)
    etat["journal"].append({"date": now_iso(), "action": "achat", "ticker": p["ticker"],
                            "eur": round(eur, 2), "prix_usd": prix_usd, "qty": qty})
    return p


def vendre(etat, ticker, taux_usd, prix_usd, raison):
    """Vente papier de toute la ligne ; deplace la position dans 'cloturees'."""
    pos = next((p for p in etat["positions"] if p["ticker"].lower() == ticker.lower()), None)
    if not pos:
        raise ValueError(f"{ticker} n'est pas en portefeuille")
    produit_usd = pos["qty"] * prix_usd
    eur_revende = produit_usd / taux_usd
    pnl_eur = round(eur_revende - pos["eur_investis"], 2)
    ligne = dict(pos)
    ligne.update({"date_cloture": now_iso(), "prix_sortie_usd": prix_usd,
                  "taux_usd_sortie": round(taux_usd, 4), "eur_revendes": round(eur_revende, 2),
                  "pnl_eur": pnl_eur, "raison_sortie": raison, "statut": "cloturee"})
    etat["positions"].remove(pos)
    etat["cloturees"].append(ligne)
    etat["journal"].append({"date": now_iso(), "action": "vente", "ticker": pos["ticker"],
                            "pnl_eur": pnl_eur, "raison": raison})
    return ligne


def jours_avant_catalyseur(pos, aujourdhui=None):
    try:
        cible = datetime.fromisoformat(pos["date_catalyseur"]).date()
    except (ValueError, TypeError):
        return None
    ref = (aujourdhui or datetime.now(timezone.utc).date())
    return (cible - ref).days


def valeur(etat, taux_usd):
    """Valeur actuelle de la sleeve : lignes valorisees + cash non investi (EUR)."""
    lignes = []
    tickers = [p["ticker"] for p in etat["positions"]]
    cours = cours_usd(tickers) if tickers else {}
    total_lignes_eur = 0.0
    for p in etat["positions"]:
        c = cours.get(p["ticker"].lower())
        val_usd = p["qty"] * c["close"] if c else p["qty"] * p["prix_entree_usd"]
        val_eur = val_usd / taux_usd
        pnl = val_eur - p["eur_investis"]
        total_lignes_eur += val_eur
        lignes.append({**p, "cours_usd": c["close"] if c else None,
                       "valeur_eur": round(val_eur, 2), "pnl_eur": round(pnl, 2),
                       "pnl_pct": round(pnl / p["eur_investis"] * 100, 2),
                       "jours_catalyseur": jours_avant_catalyseur(p)})
    return {
        "lignes": lignes,
        "valeur_lignes_eur": round(total_lignes_eur, 2),
        "cash_eur": cash_disponible(etat),
        "total_eur": round(total_lignes_eur + cash_disponible(etat), 2),
        "pnl_eur": round(total_lignes_eur - sum(p["eur_investis"] for p in etat["positions"]), 2),
    }
