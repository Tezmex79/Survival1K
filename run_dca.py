"""Point d'entree principal : execute un tick, met a jour l'etat, genere le rapport.

Usage :
    python run_dca.py                 # tick selon config.yaml :
                                     #   simulation  -> achat papier (vrais prix)
                                     #   etoro-demo  -> ordres sur le compte DEMO eToro
                                     #   etoro-real  -> DRY-RUN ; ordres reels seulement avec --execute
    python run_dca.py --status        # lecture seule : rapport sans aucun achat
    python run_dca.py --etf 20        # declare un achat ETF manuel de 20 EUR (suivi)
    python run_dca.py --execute       # requis pour passer les ordres REELS eToro
"""
import argparse
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import yaml
from dotenv import load_dotenv

from engine import broker
from engine import portfolio as pf
from engine import prices
from engine import sentiment
from engine.report import write_report
from engine.strategy import decide, variation_ponderee


def taux_usd_par_eur(exchange, cfg):
    """Proxy EUR->USD via la paire EUR/USDT de Binance (USDT ~ USD a ~0,1 % pres)."""
    t = exchange.fetch_ticker(cfg["exchange"]["taux_usd"])
    return float(t["last"])


def main():
    parser = argparse.ArgumentParser(description="Tick DCA du systeme 100 Survival")
    parser.add_argument("--status", action="store_true", help="lecture seule, aucun achat")
    parser.add_argument("--etf", type=float, metavar="EUR", help="declarer un achat ETF manuel")
    parser.add_argument("--execute", action="store_true",
                        help="autoriser les ordres REELS en mode etoro-real")
    args = parser.parse_args()

    cfg = yaml.safe_load(open(pf.BASE / "config.yaml", encoding="utf-8"))
    load_dotenv(pf.BASE / ".env")
    state = pf.load(cfg)
    mode = cfg.get("mode", "simulation")

    exchange = prices.make_exchange(cfg)

    if args.etf is not None:
        pf.declare_etf(state, args.etf)
        pf.save(state)
        print(f"ETF declare : {args.etf:.2f} EUR (total ETF : {pf.etf_total(state):.2f} EUR)")

    prix = prices.get_prices(exchange, cfg["exchange"]["paires"])
    changes = {}
    for asset in cfg["crypto"]["split"]:
        closes = prices.get_daily_closes(exchange, cfg["exchange"]["paires"][asset],
                                         days=int(cfg["crypto"]["dip"]["fenetre_jours"]) + 3)
        changes[asset] = prices.change_pct(closes, int(cfg["crypto"]["dip"]["fenetre_jours"]))

    actions = []
    var = variation_ponderee(changes, cfg["crypto"]["split"])
    orders, meta = [], {"dca_executed": False, "dip_executed": False}

    if args.status:
        pass  # lecture seule : aucun ordre
    else:
        orders, var, meta = decide(state, cfg, changes)
        if mode == "simulation":
            frais = float(cfg["crypto"]["frais_pct"])
            for o in orders:
                pf.buy(state, o["asset"], o["eur"], prix[o["asset"]], frais, o["kind"])
                actions.append(f"{o['kind']} {o['eur']:.2f} EUR -> {o['asset']} "
                               f"@{prix[o['asset']]:.2f} (papier)")
            _appliquer_compteurs(state, cfg, meta)
        elif mode.startswith("etoro"):
            api_key, user_key = os.getenv("ETORO_API_KEY"), os.getenv("ETORO_USER_KEY")
            demo = mode == "etoro-demo"
            reel = mode == "etoro-real"
            if reel and not args.execute:
                print("MODE etoro-real SANS --execute : dry-run, aucun ordre transmis.")
                for o in orders:
                    print(f"  (simule) {o['kind']} {o['eur']:.2f} EUR -> {o['asset']}")
                actions = []
            elif orders:
                taux = taux_usd_par_eur(exchange, cfg)
                for o in orders:
                    montant_usd = o["eur"] * taux
                    inst = broker.resoudre_instrument(o["asset"], api_key, user_key)
                    rep = broker.acheter_marche(inst, montant_usd, api_key, user_key, demo=demo)
                    final = broker.attendre_execution(rep.get("orderId"), api_key, user_key)
                    pf.buy(state, o["asset"], o["eur"], prix[o["asset"]],
                           float(cfg["crypto"]["frais_pct"]), o["kind"])
                    actions.append(f"{o['kind']} {o['eur']:.2f} EUR (~{montant_usd:.2f} USD) "
                                   f"-> {o['asset']} sur eToro [{'DEMO' if demo else 'REEL'}] "
                                   f"statut {final.get('status')}")
                _appliquer_compteurs(state, cfg, meta)
        else:
            raise SystemExit(f"Mode inconnu '{mode}' dans config.yaml "
                             "(simulation | etoro-demo | etoro-real)")

    drawdown = pf.update_peak_and_drawdown(state, prix)
    fg = sentiment.fear_greed()
    pf.save(state)

    bio = None
    if cfg.get("biotech", {}).get("actif"):
        from engine import biotech as bio_mod
        etat_bio = bio_mod.charger(cfg)
        bio = bio_mod.valeur(etat_bio, taux_usd_par_eur(exchange, cfg))

    write_report(state, cfg, prix, var, drawdown, fg, bio)

    p = pf.pnl(state, prix)
    fg_txt = f"F&G {fg['valeur']}/100 ({fg['label']})" if fg else "F&G indisponible"
    resume = (f"Mode {mode} | Portefeuille {p['total_sleeve']:.2f} EUR | "
              f"investi {p['investi']:.2f} EUR | P&L {p['pnl_pct']:+.2f}% | "
              f"var 7j {var:+.2f}% | drawdown {drawdown:.2f}% | {fg_txt}")
    if actions:
        print("Actions executees :")
        for a in actions:
            print(f"  - {a}")
    elif not args.status:
        print("Aucun ordre ce tick (phase terminee ou conditions non remplies).")
    print(resume)
    print("Rapport complet : data/report.md")


def _appliquer_compteurs(state, cfg, meta):
    if meta["dca_executed"]:
        state["dca_done"] += 1
    if meta["dip_executed"]:
        state["dip_reserve_eur"] = round(
            state["dip_reserve_eur"] - float(cfg["crypto"]["dip"]["tranche_eur"]), 2)
        state["last_dip_date"] = pf.now_iso()


if __name__ == "__main__":
    main()
