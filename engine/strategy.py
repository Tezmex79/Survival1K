"""Logique de decision : DCA hebdomadaire + renfort sur baisse (dip)."""
from datetime import datetime, timezone


def split_eur(eur, split):
    """Repartit un montant selon les poids du config: {actif: montant}."""
    return {a: round(eur * w, 2) for a, w in split.items()}


def variation_ponderee(changes, split):
    """Variation 7j de la sleeve crypto, ponderee par la repartition cible."""
    return sum(w * changes.get(a, 0.0) for a, w in split.items())


def actif_sous_pondere(state, split):
    """Actif le plus en dessous de sa cible (en EUR investis cumules).

    Utilise en execution eToro : le minimum ~10 USD par ordre interdit de
    decouper chaque vague ; la vague entiere part vers l'actif sous-pondere,
    ce qui maintient la repartition cible dans le temps.
    """
    totaux = {a: 0.0 for a in split}
    for t in state["trades"]:
        if t["asset"] in totaux:
            totaux[t["asset"]] += t["eur"]
    total = sum(totaux.values()) or 1.0
    return min(split, key=lambda a: totaux[a] / total - split[a])


def _jours_depuis(date_iso):
    if not date_iso:
        return 999
    then = datetime.fromisoformat(date_iso)
    return (datetime.now(timezone.utc) - then).days


def decide(state, cfg, changes):
    """Retourne (ordres, variation_7j_pct, meta) SANS muter l'etat.

    Ordres: [{"kind": "DCA"|"DIP", "asset": ..., "eur": ...}, ...]
    En simulation : chaque vague est coupee selon le split cible.
    En mode etoro-* : une seule ligne par vague (minimum ~10 USD par ordre),
    dirigee vers l'actif sous-pondere.
    """
    crypto = cfg["crypto"]
    split = crypto["split"]
    mode = cfg.get("mode", "simulation")
    mono_actif = mode.startswith("etoro")
    orders = []
    meta = {"dca_executed": False, "dip_executed": False}
    var = variation_ponderee(changes, split)

    if not crypto.get("actif", True):
        return orders, var, meta  # sleeve crypto en sommeil (ex. allocation 0)

    # 1) Vague DCA de base (une seule par tick)
    tranche = float(crypto["dca"]["tranche_eur"])
    if state["dca_done"] < state["dca_planned"] and state["cash_eur"] >= tranche:
        if mono_actif:
            orders.append({"kind": "DCA", "asset": actif_sous_pondere(state, split),
                           "eur": tranche})
        else:
            for asset, part in split_eur(tranche, split).items():
                orders.append({"kind": "DCA", "asset": asset, "eur": part})
        meta["dca_executed"] = True

    # 2) Renfort sur baisse : variation 7j <= seuil, reserve dispo, cooldown respecte
    dip = crypto["dip"]
    tranche_dip = float(dip["tranche_eur"])
    var_ok = var <= float(dip["seuil_pct"])
    reserve_ok = state["dip_reserve_eur"] >= tranche_dip
    cash_ok = state["cash_eur"] >= tranche_dip
    cooldown_ok = _jours_depuis(state.get("last_dip_date")) >= int(dip["cooldown_jours"])
    if var_ok and reserve_ok and cash_ok and cooldown_ok:
        if mono_actif:
            orders.append({"kind": "DIP", "asset": actif_sous_pondere(state, split),
                           "eur": tranche_dip})
        else:
            for asset, part in split_eur(tranche_dip, split).items():
                orders.append({"kind": "DIP", "asset": asset, "eur": part})
        meta["dip_executed"] = True

    return orders, var, meta
