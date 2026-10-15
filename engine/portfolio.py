"""Portefeuille papier persistant (data/state.json) - etat unique, auditable."""
import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_state(cfg):
    crypto = cfg["crypto"]
    return {
        "created_at": now_iso(),
        "mode": cfg.get("mode", "simulation"),
        "crypto_budget_eur": float(cfg["allocation"]["crypto_eur"]),
        "cash_eur": float(cfg["allocation"]["crypto_eur"]),
        "dca_done": 0,
        "dca_planned": int(crypto["dca"]["semaines"]),
        "dip_reserve_eur": float(crypto["dip"]["reserve_eur"]),
        "last_dip_date": None,
        "holdings": {a: {"qty": 0.0, "cost_eur": 0.0} for a in crypto["split"]},
        "trades": [],
        "etf_deposits": [],
        "peak_value_eur": 0.0,
    }


def load(cfg):
    DATA.mkdir(exist_ok=True)
    path = DATA / "state.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    state = default_state(cfg)
    save(state)
    return state


def save(state):
    DATA.mkdir(exist_ok=True)
    (DATA / "state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def buy(state, asset, eur, price, fee_pct, kind):
    """Achete `eur` (frais deduits) de `asset` au `price` donne. Retourne le trade."""
    fee = round(eur * fee_pct / 100, 6)
    qty = round((eur - fee) / price, 8)
    h = state["holdings"][asset]
    h["qty"] = round(h["qty"] + qty, 8)
    h["cost_eur"] = round(h["cost_eur"] + eur, 2)
    state["cash_eur"] = round(state["cash_eur"] - eur, 2)
    trade = {
        "date": now_iso(), "kind": kind, "asset": asset,
        "eur": round(eur, 2), "price": price, "qty": qty, "fee": fee,
    }
    state["trades"].append(trade)
    return trade


def crypto_value(state, prices):
    return sum(h["qty"] * prices[a] for a, h in state["holdings"].items() if a in prices)


def invested_eur(state):
    return round(sum(h["cost_eur"] for h in state["holdings"].values()), 2)


def pnl(state, prices):
    investi = invested_eur(state)
    valeur = crypto_value(state, prices)
    pnl_pct = (valeur / investi - 1) * 100 if investi > 0 else 0.0
    return {
        "valeur_crypto": round(valeur, 2),
        "cash": state["cash_eur"],
        "total_sleeve": round(valeur + state["cash_eur"], 2),
        "investi": investi,
        "pnl_pct": round(pnl_pct, 2),
    }


def update_peak_and_drawdown(state, prices):
    """Met a jour le pic de valeur et retourne le drawdown courant en % (jamais negatif)."""
    total = crypto_value(state, prices) + state["cash_eur"]
    if total > state["peak_value_eur"]:
        state["peak_value_eur"] = round(total, 2)
    if state["peak_value_eur"] == 0:
        return 0.0
    return round(max((1 - total / state["peak_value_eur"]) * 100, 0.0), 2)


def declare_etf(state, eur):
    state["etf_deposits"].append({"date": now_iso(), "eur": round(float(eur), 2)})
    return state["etf_deposits"][-1]


def etf_total(state):
    return round(sum(d["eur"] for d in state["etf_deposits"]), 2)
