"""Backtest roulant : Lump sum vs DCA pur vs DCA + dip, sur donnees Binance reelles.

Chaque date de depart (glissant toutes les `pas` jours) simule la phase d'entree
de la strategie (4 vagues hebdo + renforts dip), puis la conservation jusqu'a
la derniere close disponible. Comparaison a budget egal (40 EUR, cash non
depense compte dans la valeur finale).
"""
from datetime import datetime, timezone

import pandas as pd

from .strategy import split_eur, variation_ponderee


def _achete(portefeuille, asset, eur, price, frais_pct):
    qty = (eur * (1 - frais_pct / 100)) / price
    portefeuille["qty"][asset] += qty
    portefeuille["cash"] -= eur


def _simule_entree(i, closes, cfg):
    """Simule la phase d'entree depuis l'indice i, retourne (qty, cash_restant, nb_dips)."""
    crypto = cfg["crypto"]
    split = crypto["split"]
    frais = float(crypto["frais_pct"])
    pf = {"qty": {a: 0.0 for a in split}, "cash": float(cfg["allocation"]["crypto_eur"])}
    semaines = int(crypto["dca"]["semaines"])
    tranche = float(crypto["dca"]["tranche_eur"])
    dip = crypto["dip"]
    fen = int(dip["fenetre_jours"])
    cooldown = int(dip["cooldown_jours"])
    reserve = float(dip["reserve_eur"])
    dip_tranche = float(dip["tranche_eur"])
    nb_dips = 0
    dernier_dip_j = -999

    fin_entree = i + semaines * 7
    # phase d'entree : un achat DCA par semaine, dip verifie chaque jour
    for j in range(i, min(fin_entree, len(next(iter(closes.values()))) - 1)):
        prix_jour = {a: closes[a][j][1] for a in split}
        # vague DCA a j = i, i+7, i+14, i+21
        if (j - i) % 7 == 0 and (j - i) // 7 < semaines and pf["cash"] >= tranche:
            for asset, part in split_eur(tranche, split).items():
                _achete(pf, asset, part, prix_jour[asset], frais)
        # renfort dip
        if j - i >= fen + 1:
            changes = {
                a: (closes[a][j][1] / closes[a][j - fen][1] - 1) * 100 for a in split
            }
            var = variation_ponderee(changes, split)
            if (
                var <= float(dip["seuil_pct"])
                and reserve >= dip_tranche
                and pf["cash"] >= dip_tranche
                and j - dernier_dip_j >= cooldown
            ):
                for asset, part in split_eur(dip_tranche, split).items():
                    _achete(pf, asset, part, prix_jour[asset], frais)
                reserve -= dip_tranche
                nb_dips += 1
                dernier_dip_j = j
    return pf, nb_dips


def run(closes, cfg, pas=7):
    """Retourne un DataFrame des P&L finaux % par date de depart et par strategie."""
    crypto = cfg["crypto"]
    split = crypto["split"]
    frais = float(crypto["frais_pct"])
    budget = float(cfg["allocation"]["crypto_eur"])
    semaines = int(crypto["dca"]["semaines"])
    fin = len(next(iter(closes.values())))
    assets = list(split)
    derniere_close = {a: closes[a][-1][1] for a in assets}

    lignes = []
    for i in range(int(crypto["dip"]["fenetre_jours"]) + 1, fin - semaines * 7 - 1, pas):
        date = datetime.fromtimestamp(closes[assets[0]][i][0] / 1000, tz=timezone.utc)
        # lump sum : tout au jour i
        pf_lump = {"qty": {a: 0.0 for a in assets}, "cash": budget}
        for asset, part in split_eur(budget, split).items():
            _achete(pf_lump, asset, part, closes[asset][i][1], frais)
        # DCA pur et DCA + dip
        pf_dca, _ = _simule_entree(i, closes, cfg)
        # DCA pur : desactive le dip en vidant la reserve
        cfg_pur = dict(cfg)
        crypto_pur = dict(cfg["crypto"])
        crypto_pur["dip"] = dict(cfg["crypto"]["dip"], reserve_eur=0)
        cfg_pur["crypto"] = crypto_pur
        pf_pur, _ = _simule_entree(i, closes, cfg_pur)

        def valeur_finale(pf):
            holdings = sum(pf["qty"][a] * derniere_close[a] for a in assets)
            return holdings + pf["cash"]

        lignes.append({
            "depart": date.strftime("%Y-%m-%d"),
            "lump_sum_pct": round((valeur_finale(pf_lump) / budget - 1) * 100, 2),
            "dca_pur_pct": round((valeur_finale(pf_pur) / budget - 1) * 100, 2),
            "dca_dip_pct": round((valeur_finale(pf_dca) / budget - 1) * 100, 2),
        })
    return pd.DataFrame(lignes)


def stats(df):
    """Statistiques par strategie : mediane, moyenne, min, max du P&L final %."""
    colonnes = ["lump_sum_pct", "dca_pur_pct", "dca_dip_pct"]
    out = {}
    for c in colonnes:
        s = df[c]
        out[c] = {
            "mediane": round(float(s.median()), 2),
            "moyenne": round(float(s.mean()), 2),
            "min": round(float(s.min()), 2),
            "max": round(float(s.max()), 2),
            "taux_reussite_pct": round(float((s > 0).mean() * 100), 1),
        }
    return out
