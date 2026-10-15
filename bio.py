"""CLI de la sleeve biotech : lignes evenementielles FDA/EMA (portefeuille papier).

Usage :
    python bio.py                                        # statut + valeur de la sleeve
    python bio.py buy CRSP 10 "PDUFA exa-cel" 2026-12-16 --nom "CRISPR Therapeutics"
    python bio.py sell CRSP "catalyseur resolu : approbation"
    python bio.py journal                                # historique des operations

Les cours viennent de Stooq (US, USD) ; la conversion EUR/USD du jour vient de
Binance EUR/USDT. Regles (config.yaml > biotech) appliquees : max par ligne,
max positions, cash disponible.
"""
import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import yaml

from engine import biotech
from engine import prices


def taux_usd(cfg):
    ex = prices.make_exchange(cfg)
    return float(ex.fetch_ticker(cfg["exchange"]["taux_usd"])["last"])


def main():
    parser = argparse.ArgumentParser(description="Sleeve biotech 100 Survival")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status", help="statut de la sleeve (defaut)")
    p_buy = sub.add_parser("buy", help="achat papier d'une ligne evenementielle")
    p_buy.add_argument("ticker")
    p_buy.add_argument("eur", type=float)
    p_buy.add_argument("catalyseur")
    p_buy.add_argument("date_catalyseur", help="AAAA-MM-JJ")
    p_buy.add_argument("--nom", default="")
    p_sell = sub.add_parser("sell", help="vente papier d'une ligne")
    p_sell.add_argument("ticker")
    p_sell.add_argument("raison", nargs="?", default="sortie manuelle")
    sub.add_parser("journal", help="historique des operations")
    sub.add_parser("check", help="controle radar : alertes stop-loss et catalyseurs")
    p_track = sub.add_parser("track", help="declarer une position REELLE detenue hors papier")
    p_track.add_argument("ticker", help="symbole Yahoo, ex. MEDIC.PA")
    p_track.add_argument("montant_eur", type=float)
    p_track.add_argument("--nom", default="")
    p_track.add_argument("--note", default="")
    p_untrack = sub.add_parser("untrack", help="retirer une position reelle declaree")
    p_untrack.add_argument("ticker")
    args = parser.parse_args()
    if not args.cmd:
        args.cmd = "status"

    cfg = yaml.safe_load(open(biotech.BASE / "config.yaml", encoding="utf-8"))
    regles = cfg["biotech"]
    etat = biotech.charger(cfg)
    t = taux_usd(cfg)

    if args.cmd == "buy":
        ticker = args.ticker.upper()
        cours = biotech.cours_usd([ticker])
        if ticker.lower() not in cours:
            raise SystemExit(f"Cours introuvable pour {ticker} (ticker US attendu, ex. BBIO)")
        prix = cours[ticker.lower()]["close"]
        if args.eur > float(regles["max_par_ligne_eur"]):
            raise SystemExit(f"Refus : {args.eur} EUR > max par ligne ({regles['max_par_ligne_eur']} EUR)")
        if len(etat["positions"]) >= int(regles["max_positions"]):
            raise SystemExit(f"Refus : nombre max de positions atteint ({regles['max_positions']})")
        if args.eur > biotech.cash_disponible(etat):
            raise SystemExit(f"Refus : cash restant {biotech.cash_disponible(etat)} EUR < {args.eur} EUR")
        p = biotech.acheter(etat, ticker, args.eur, t, prix, args.catalyseur,
                            args.date_catalyseur, args.nom)
        biotech.sauver(etat)
        print(f"Achat papier : {p['qty']} {ticker} @ {prix} USD "
              f"({args.eur} EUR, taux {t:.4f}) — catalyseur {args.catalyseur} le {args.date_catalyseur}")
        return

    if args.cmd == "sell":
        ticker = args.ticker.upper()
        cours = biotech.cours_usd([ticker])
        prix = cours.get(ticker.lower(), {}).get("close")
        if not prix:
            raise SystemExit(f"Cours introuvable pour {ticker}")
        ligne = biotech.vendre(etat, ticker, t, prix, args.raison)
        biotech.sauver(etat)
        print(f"Vente papier {ticker} @ {prix} USD — P&L {ligne['pnl_eur']:+.2f} EUR "
              f"({ligne['raison_sortie']})")
        return

    if args.cmd == "track":
        ticker = args.ticker.upper()
        cours = biotech.cours_usd([ticker])
        c = cours.get(ticker.lower())
        if not c:
            raise SystemExit(f"Cours introuvable pour {ticker} (symbole Yahoo attendu, ex. MEDIC.PA)")
        p = biotech.suivre_reelle(etat, ticker, args.montant_eur, c["close"],
                                  c.get("devise", ""), t, args.nom, args.note)
        biotech.sauver(etat)
        print(f"Position reelle declaree : {p['qty']} {ticker} "
              f"({args.montant_eur:.2f} EUR, cours {c['close']} {c.get('devise')}) — "
              f"le P&L est suivi a partir de la declaration ; donner la quantite exacte "
              f"eToro plus tard pour affiner la base")
        return

    if args.cmd == "untrack":
        avant = len(etat["positions_reelles"])
        etat["positions_reelles"] = [p for p in etat["positions_reelles"]
                                     if p["ticker"].upper() != args.ticker.upper()]
        if len(etat["positions_reelles"]) == avant:
            raise SystemExit(f"{args.ticker} n'est pas une position reelle declaree")
        biotech.sauver(etat)
        print(f"Position reelle {args.ticker} retiree du suivi.")
        return

    if args.cmd == "check":
        v = biotech.valeur(etat, t)
        alertes = []
        for l in v["lignes"]:
            if l["pnl_pct"] <= float(regles["stop_loss_pct"]):
                alertes.append(f"STOP-LOSS {l['ticker']} : {l['pnl_pct']:+.2f}% "
                               f"<= {regles['stop_loss_pct']}% -> VENDRE")
            jc = l["jours_catalyseur"]
            if jc is not None and jc <= 0:
                alertes.append(f"CATALYSEUR ECHU {l['ticker']} ({l['date_catalyseur']}) "
                               f"-> verifier l'issue puis VENDRE")
            elif jc is not None and jc <= 2:
                alertes.append(f"IMMINENT {l['ticker']} : catalyseur {l['date_catalyseur']} "
                               f"(J{jc}) -> surveiller")
        print(f"Radar biotech : {len(v['lignes'])} ligne(s), P&L ouvert "
              f"{v['pnl_eur']:+.2f} EUR, cash {v['cash_eur']:.2f} EUR")
        for l in v["lignes"]:
            jc = l["jours_catalyseur"]
            print(f"  {l['ticker']:<6} {l['pnl_pct']:+7.2f}%  catalyseur J{jc if jc is not None else '?'}")
        if alertes:
            print("ALERTES :")
            for a in alertes:
                print(f"  ! {a}")
        else:
            print("Aucune alerte.")
        return

    if args.cmd == "journal":
        for e in etat["journal"][-20:]:
            print(f"{e['date'][:16]} {e['action']:>6} {e['ticker']:<6} {e}")
        return

    v = biotech.valeur(etat, t)
    print(f"Sleeve biotech : {v['total_eur']:.2f} EUR "
          f"(lignes {v['valeur_lignes_eur']:.2f} + cash {v['cash_eur']:.2f}) | "
          f"P&L ouvert {v['pnl_eur']:+.2f} EUR | taux EUR/USD {t:.4f}")
    if not v["lignes"]:
        print("Aucune ligne ouverte. Watchlist : data/biotech_watchlist.md")
    for l in v["lignes"]:
        jc = l["jours_catalyseur"]
        jc_txt = f"{jc} j" if jc is not None else "n/d"
        print(f"  {l['ticker']:<6} {l['nom'][:28]:<28} {l['valeur_eur']:>6.2f} EUR "
              f"({l['pnl_eur']:+5.2f} / {l['pnl_pct']:+6.2f} %) | catalyseur: "
              f"{l['catalyseur']} ({l['date_catalyseur']}, J{jc_txt})")
    if v.get("reelles"):
        print(f"Positions reelles declarees : {v['valeur_reelles_eur']:.2f} EUR")
        for l in v["reelles"]:
            print(f"  {l['ticker']:<9} {l['nom'][:26]:<26} {l['valeur_eur']:>8.2f} EUR "
                  f"({l['pnl_eur']:+7.2f} / {l['pnl_pct']:+6.2f} % depuis declaration)")


if __name__ == "__main__":
    main()
