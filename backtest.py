"""CLI de backtest : compare lump sum vs DCA pur vs DCA+dip sur ~3 ans de donnees reelles.

Usage : python backtest.py [--days 1095] [--pas 7]
"""
import argparse
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import yaml

from engine import prices
from engine.backtest import run, stats
from engine.portfolio import BASE, DATA


def main():
    parser = argparse.ArgumentParser(description="Backtest DCA 100 Survival")
    parser.add_argument("--days", type=int, default=1095, help="jours d'historique (defaut 1095)")
    parser.add_argument("--pas", type=int, default=7, help="pas entre dates de depart (defaut 7)")
    args = parser.parse_args()

    cfg = yaml.safe_load(open(BASE / "config.yaml", encoding="utf-8"))
    exchange = prices.make_exchange(cfg)
    print(f"Telechargement {args.days} jours de closes quotidiennes "
          f"({', '.join(cfg['exchange']['paires'].values())})...")
    closes = {
        asset: prices.get_daily_closes(exchange, symbol, args.days)
        for asset, symbol in cfg["exchange"]["paires"].items()
    }
    for asset, rows in closes.items():
        print(f"  {asset}: {len(rows)} jours, dernier close {rows[-1][1]:.2f} EUR")

    df = run(closes, cfg, pas=args.pas)
    s = stats(df)
    seuil = int(cfg["crypto"]["dip"]["seuil_pct"])
    tranche = int(cfg["crypto"]["dca"]["tranche_eur"])
    semaines = int(cfg["crypto"]["dca"]["semaines"])
    noms = {
        "lump_sum_pct": "Lump sum (tout au jour 1)",
        "dca_pur_pct": f"DCA pur ({semaines}x{tranche} EUR hebdo)",
        "dca_dip_pct": f"DCA + renfort dip ({seuil}%/7j)",
    }
    frais_pct = float(cfg["crypto"]["frais_pct"])
    print(f"\n{len(df)} dates de depart testees, glissant tous les {args.pas} jours, "
          f"conservation jusqu'a aujourd'hui. Budget "
          f"{int(cfg['allocation']['crypto_eur'])} EUR, frais {frais_pct}%/ordre.")
    print("\n| Strategie | Mediane | Moyenne | Min | Max | Taux de gain |")
    print("|---|---|---|---|---|---|")
    lignes_md = [
        f"# Backtest DCA - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"- Donnees : {args.days} jours de closes quotidiennes Binance "
        f"({', '.join(cfg['exchange']['paires'].values())})",
        f"- {len(df)} dates de depart glissantes (pas {args.pas} j), conservation jusqu'a la fin",
        f"- Budget {int(cfg['allocation']['crypto_eur'])} EUR, frais {frais_pct} %/ordre, split "
        f"{'/'.join(f'{a} {int(w*100)}%' for a, w in cfg['crypto']['split'].items())}",
        "",
        "| Strategie | Mediane | Moyenne | Min | Max | Taux de gain |",
        "|---|---|---|---|---|---|",
    ]
    for col, nom in noms.items():
        st = s[col]
        ligne = (f"| {nom} | {st['mediane']:+.2f}% | {st['moyenne']:+.2f}% "
                 f"| {st['min']:+.2f}% | {st['max']:+.2f}% | {st['taux_reussite_pct']:.0f}% |")
        print(ligne)
        lignes_md.append(ligne)

    meilleur = max(s, key=lambda c: s[c]["moyenne"])
    concl = f"\nMeilleure moyenne : {noms[meilleur]} ({s[meilleur]['moyenne']:+.2f}%)."
    print(concl)
    lignes_md += ["", concl, "",
                  "*Un backtest decrit le passe, il ne garantit rien sur le futur.*", ""]
    DATA.mkdir(exist_ok=True)
    (DATA / "backtest_report.md").write_text("\n".join(lignes_md), encoding="utf-8")
    print("Rapport : data/backtest_report.md")


if __name__ == "__main__":
    main()
