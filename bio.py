"""CLI de la sleeve biotech : lignes evenementielles FDA/EMA.

Usage :
    python bio.py                                        # statut + valeur de la sleeve
    python bio.py buy CRSP 10 "PDUFA exa-cel" 2026-12-16 --nom "CRISPR Therapeutics"
    python bio.py sell CRSP "catalyseur resolu"
    python bio.py check                                  # radar : alertes stop-loss/catalyseurs
    python bio.py liquider MEDCL.PA 40 --execute         # vente partielle d'une position reelle
    python bio.py journal                                # historique

Execution selon config.yaml > mode :
    simulation  -> portefeuille papier uniquement
    etoro-demo  -> papier + ordres MIRROIR sur le compte DEMO eToro
    etoro-real  -> papier + ordres REELS, mais seulement avec le flag --execute

Positions reelles protegees (config.yaml > etoro.protection_positions_reelles) :
    jamais vendues automatiquement ; `liquider` agit sur le compte REEL avec
    plafond cumule verifie, et exige --execute.
"""
import argparse
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import json as _json
import urllib.request as _urllib_req

import yaml
from dotenv import load_dotenv

from engine import biotech
from engine import broker

load_dotenv(biotech.BASE / ".env")


def taux_usd(cfg):
    """Taux EUR/USD via Yahoo (leger, sans ccxt) avec cache disque en secours.

    Le check local de la tache Windows tourne toutes les 15 min : importer ccxt
    (des centaines de Mo) pour un simple taux provoquait un pic CPU de ~5 s a
    chaque lancement — remplacé par un simple appel urllib.
    """
    cache = biotech.DATA / "taux_usd.txt"
    try:
        req = _urllib_req.Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?interval=1d&range=1d",
            headers={"User-Agent": "Mozilla/5.0"})
        with _urllib_req.urlopen(req, timeout=10) as r:
            meta = _json.loads(r.read().decode("utf-8"))["chart"]["result"][0]["meta"]
        taux = float(meta["regularMarketPrice"])
        cache.write_text(str(taux), encoding="utf-8")
        return taux
    except Exception:
        if cache.exists():
            return float(cache.read_text(encoding="utf-8").strip() or 1.12)
        return 1.12  # dernier recours devolu explicitement dans le journal si utilise


def _cles_etoro():
    return os.getenv("ETORO_API_KEY"), os.getenv("ETORO_USER_KEY")


def _chercher_cle(obj, cle):
    """Cherche recursivement une cle dans la reponse JSON eToro (schema variable)."""
    if isinstance(obj, dict):
        if cle in obj and obj[cle] is not None:
            return obj[cle]
        for v in obj.values():
            r = _chercher_cle(v, cle)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _chercher_cle(v, cle)
            if r is not None:
                return r
    return None


def _executer_achat_etoro(cfg, o, api_key, user_key, demo, taux):
    """Passe l'ordre achat sur eToro, attend l'execution, retourne les infos."""
    symbole_etoro = o.get("symbole_etoro", o["ticker"])
    inst = broker.resoudre_instrument(symbole_etoro, api_key, user_key)
    montant_usd = o["eur"] * taux
    rep = broker.acheter_marche(inst, montant_usd, api_key, user_key, demo=demo)
    final = broker.attendre_execution(rep.get("orderId"), api_key, user_key, demo=demo)
    position_id = _chercher_cle(final, "positionId")
    return {"orderId": rep.get("orderId"), "referenceId": rep.get("referenceId"),
            "status": final.get("status"), "positionId": position_id,
            "montant_usd": round(montant_usd, 2), "compte": "demo" if demo else "reel"}


def main():
    parser = argparse.ArgumentParser(description="Sleeve biotech 100 Survival")
    parser.add_argument("--execute", action="store_true",
                        help="autoriser les ordres REELS eToro (etoro-real / liquider)")
    parser.add_argument("--local", action="store_true",
                        help="check local (tache Windows de reveil) : ne met PAS a jour "
                             "last_radar.txt pour ne pas supprimer le radar de l'agent")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status", help="statut de la sleeve (defaut)")
    p_buy = sub.add_parser("buy", help="achat d'une ligne evenementielle")
    p_buy.add_argument("ticker")
    p_buy.add_argument("eur", type=float)
    p_buy.add_argument("catalyseur")
    p_buy.add_argument("date_catalyseur", help="AAAA-MM-JJ")
    p_buy.add_argument("--nom", default="")
    p_buy.add_argument("--etoro", default=None, dest="symbole_etoro",
                       help="symbole eToro si different (ex. MEDCL.PA)")
    p_ren = sub.add_parser("renforcer", help="renfort d'une ligne existante (papier + eToro selon mode)")
    p_ren.add_argument("ticker")
    p_ren.add_argument("eur", type=float)
    p_ren.add_argument("--etoro", default=None, dest="symbole_etoro")
    p_sell = sub.add_parser("sell", help="vente d'une ligne")
    p_sell.add_argument("ticker")
    p_sell.add_argument("raison", nargs="?", default="sortie manuelle")
    sub.add_parser("journal", help="historique des operations")
    sub.add_parser("check", help="controle radar : alertes stop-loss et catalyseurs")
    p_track = sub.add_parser("track", help="declarer une position REELLE detenue hors papier")
    p_track.add_argument("ticker", help="symbole Yahoo, ex. MEDCL.PA")
    p_track.add_argument("montant_eur", type=float)
    p_track.add_argument("--nom", default="")
    p_track.add_argument("--note", default="")
    p_untrack = sub.add_parser("untrack", help="retirer une position reelle declaree")
    p_untrack.add_argument("ticker")
    p_liq = sub.add_parser("liquider", help="vente partielle d'une position reelle PROTEGEE (reel, --execute requis)")
    p_liq.add_argument("ticker")
    p_liq.add_argument("montant_eur", type=float)
    args = parser.parse_args()
    if not args.cmd:
        args.cmd = "status"

    cfg = yaml.safe_load(open(biotech.BASE / "config.yaml", encoding="utf-8"))
    regles = cfg["biotech"]
    mode = cfg.get("mode", "simulation")
    etat = biotech.charger(cfg)
    t = taux_usd(cfg)
    api_key, user_key = _cles_etoro()

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

        ordre = {"ticker": ticker, "eur": args.eur, "symbole_etoro": args.symbole_etoro or ticker}
        etoro_info = None
        if mode == "etoro-real" and not args.execute:
            print(f"MODE etoro-real SANS --execute : dry-run, rien n'est transmis.")
            print(f"  (simule) achat {args.eur:.2f} EUR {ticker} @ {prix} USD — {args.catalyseur} ({args.date_catalyseur})")
            return
        if mode.startswith("etoro"):
            etoro_info = _executer_achat_etoro(cfg, ordre, api_key, user_key,
                                               demo=(mode == "etoro-demo"), taux=t)
            print(f"Ordre eToro [{'DEMO' if mode == 'etoro-demo' else 'REEL'}] : "
                  f"{etoro_info['montant_usd']} USD -> {ticker}, statut {etoro_info['status']}")

        p = biotech.acheter(etat, ticker, args.eur, t, prix, args.catalyseur,
                            args.date_catalyseur, args.nom)
        p["symbole_etoro"] = ordre["symbole_etoro"]
        if etoro_info:
            p["etoro"] = etoro_info
        biotech.sauver(etat)
        print(f"Achat : {p['qty']} {ticker} @ {prix} USD ({args.eur} EUR, taux {t:.4f}) "
              f"— catalyseur {args.catalyseur} le {args.date_catalyseur}")
        return

    if args.cmd == "renforcer":
        ticker = args.ticker.upper()
        pos = next((p for p in etat["positions"] if p["ticker"] == ticker), None)
        if not pos:
            raise SystemExit(f"{ticker} n'est pas en portefeuille (utiliser buy)")
        cours = biotech.cours_usd([ticker])
        prix = cours.get(ticker.lower(), {}).get("close")
        if not prix:
            raise SystemExit(f"Cours introuvable pour {ticker}")
        delta = round(pos["eur_investis"] + args.eur - float(regles["max_par_ligne_eur"]), 2)
        if delta > 0.005:
            raise SystemExit(f"Refus : la ligne atteindrait {pos['eur_investis'] + args.eur:.2f} EUR "
                             f"> plafond {regles['max_par_ligne_eur']} EUR")
        if args.eur > biotech.cash_disponible(etat):
            raise SystemExit(f"Refus : cash {biotech.cash_disponible(etat)} EUR < {args.eur} EUR")

        ordre = {"ticker": ticker, "eur": args.eur, "symbole_etoro": args.symbole_etoro or pos.get("symbole_etoro", ticker)}
        etoro_info = None
        if mode == "etoro-real" and not args.execute:
            print(f"MODE etoro-real SANS --execute : dry-run. (simule) renfort {args.eur:.2f} EUR {ticker} @ {prix} USD")
            return
        if mode.startswith("etoro"):
            etoro_info = _executer_achat_etoro(cfg, ordre, api_key, user_key,
                                               demo=(mode == "etoro-demo"), taux=t)
            print(f"Ordre eToro [{'DEMO' if mode == 'etoro-demo' else 'REEL'}] : "
                  f"{etoro_info['montant_usd']} USD -> {ticker}, statut {etoro_info['status']}")

        montant_usd = args.eur * t
        qty = round(montant_usd / prix, 4)
        pos["qty"] = round(pos["qty"] + qty, 4)
        pos["eur_investis"] = round(pos["eur_investis"] + args.eur, 2)
        if etoro_info:
            pos.setdefault("etoro", {}).update(etoro_info)
        etat["journal"].append({"date": biotech.now_iso(), "action": "renfort",
                                "ticker": ticker, "eur": round(args.eur, 2),
                                "prix_usd": prix, "qty": qty})
        biotech.sauver(etat)
        print(f"Renfort : +{qty} {ticker} @ {prix} USD ({args.eur} EUR) — "
              f"ligne {pos['eur_investis']:.2f} EUR au total")
        return

    if args.cmd == "sell":
        ticker = args.ticker.upper()
        pos = next((p for p in etat["positions"] if p["ticker"] == ticker), None)
        if not pos:
            raise SystemExit(f"{ticker} n'est pas en portefeuille")
        cours = biotech.cours_usd([ticker])
        prix = cours.get(ticker.lower(), {}).get("close")
        if not prix:
            raise SystemExit(f"Cours introuvable pour {ticker}")

        if mode == "etoro-real" and not args.execute:
            print(f"MODE etoro-real SANS --execute : dry-run, rien n'est transmis.")
            print(f"  (simule) vente {ticker} @ {prix} USD — {args.raison}")
            return
        if mode.startswith("etoro") and pos.get("etoro"):
            e = pos["etoro"]
            demo = mode == "etoro-demo"
            position_id = e.get("positionId")
            inst = broker.resoudre_instrument(pos.get("symbole_etoro", ticker), api_key, user_key)
            if not position_id:
                trouve = broker.position_ouverte(inst, api_key, user_key, demo=demo)
                position_id = trouve and trouve["positionId"]
            if position_id:
                rep = broker.vendre_marche(position_id, inst, None, api_key, user_key, demo=demo)
                print(f"Vente eToro [{'DEMO' if demo else 'REEL'}] transmise "
                      f"(position {position_id}) : {str(rep)[:140]}")
            else:
                print(f"ATTENTION : positionId eToro introuvable pour {ticker} — "
                      f"cloturer manuellement sur l'app, la ligne papier est soldée.")

        ligne = biotech.vendre(etat, ticker, t, prix, args.raison)
        biotech.sauver(etat)
        print(f"Vente {ticker} @ {prix} USD — P&L {ligne['pnl_eur']:+.2f} EUR ({ligne['raison_sortie']})")
        return

    if args.cmd == "liquider":
        # Vente partielle d'une position reelle PROTEGEE : compte REEL + --execute + plafond cumule
        ticker = args.ticker.upper()
        protection = cfg.get("etoro", {}).get("protection_positions_reelles", {}).get(ticker)
        if not protection:
            raise SystemExit(f"{ticker} n'est pas une position protegee declaree dans config.yaml")
        plafond = float(protection["vente_max_eur_cumulee"])
        deja_vendu = etat.setdefault("ventes_reelles", {}).get(ticker, 0.0)
        if deja_vendu + args.montant_eur > plafond:
            raise SystemExit(f"REFUS : plafond {plafond} EUR — deja vendu {deja_vendu:.2f} EUR, "
                             f"demande {args.montant_eur:.2f} EUR")
        cours = biotech.cours_usd([ticker])
        c = cours.get(ticker.lower())
        if not c:
            raise SystemExit(f"Cours introuvable pour {ticker}")
        cours_eur = c["close"] / biotech.taux_si_usd(c.get("devise", "EUR"), t)
        unites = round(args.montant_eur / cours_eur, 4)
        if not args.execute:
            print(f"DRY-RUN (compte REEL, --execute requis) : vendre {unites} {ticker} "
                  f"~{args.montant_eur:.2f} EUR @ {cours_eur:.2f} EUR "
                  f"[cumul apres: {deja_vendu + args.montant_eur:.2f}/{plafond} EUR]")
            return
        inst = broker.resoudre_instrument(protection.get("symbole_etoro", ticker), api_key, user_key)
        pos = broker.position_ouverte(inst, api_key, user_key, demo=False)
        if not pos:
            raise SystemExit(f"Position ouverte {ticker} introuvable sur le compte REEL eToro")
        if pos["units"] and unites > pos["units"]:
            unites = pos["units"]
        rep = broker.vendre_marche(pos["positionId"], inst, unites, api_key, user_key, demo=False)
        etat["ventes_reelles"][ticker] = round(deja_vendu + args.montant_eur, 2)
        etat["journal"].append({"date": biotech.now_iso(), "action": "liquider",
                                "ticker": ticker, "eur": args.montant_eur,
                                "unites": unites, "reponse": str(rep)[:200]})
        biotech.sauver(etat)
        print(f"Vente partielle REELLE transmise : {unites} {ticker} (~{args.montant_eur:.2f} EUR) "
              f"[cumul {etat['ventes_reelles'][ticker]}/{plafond} EUR] — {str(rep)[:120]}")
        return

    if args.cmd == "track":
        ticker = args.ticker.upper()
        cours = biotech.cours_usd([ticker])
        c = cours.get(ticker.lower())
        if not c:
            raise SystemExit(f"Cours introuvable pour {ticker} (symbole Yahoo attendu, ex. MEDCL.PA)")
        p = biotech.suivre_reelle(etat, ticker, args.montant_eur, c["close"],
                                  c.get("devise", ""), t, args.nom, args.note)
        biotech.sauver(etat)
        print(f"Position reelle declaree : {p['qty']} {ticker} ({args.montant_eur:.2f} EUR, "
              f"cours {c['close']} {c.get('devise')}) — donner la quantite exacte eToro "
              f"plus tard pour affiner la base")
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
        from datetime import datetime
        v = biotech.valeur(etat, t)
        alertes = []
        maintenant = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        for l in v["lignes"]:
            if l["pnl_pct"] <= float(regles["stop_loss_pct"]):
                alertes.append(f"STOP-LOSS {l['ticker']} : {l['pnl_pct']:+.2f}% "
                               f"<= {regles['stop_loss_pct']}% -> VENDRE")
            jc = l["jours_catalyseur"]
            if jc is not None and jc <= 0:
                alertes.append(f"CATALYSEUR ECHU {l['ticker']} ({l['date_catalyseur']}) "
                               f"-> verifier l'issue puis VENDRE")
            elif jc is not None and jc <= 2:
                alertes.append(f"IMMINENT {l['ticker']} : catalyseur {l['date_catalyseur']} (J{jc}) -> surveiller")
        print(f"Radar biotech le {maintenant} : {len(v['lignes'])} ligne(s), "
              f"P&L ouvert {v['pnl_eur']:+.2f} EUR, cash {v['cash_eur']:.2f} EUR, mode {mode}")
        if not args.local:
            (biotech.DATA / "last_radar.txt").write_text(
                datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
        print(f"{'Ticker':<7}{'Qty':>8}{'PRU':>9}{'Cours':>9}{'Valeur €':>9}"
              f"{'P&L €':>8}{'P&L %':>8}  Catalyseur")
        for l in v["lignes"]:
            jc = l["jours_catalyseur"]
            print(f"{l['ticker']:<7}{l['qty']:>8.4f}{l['prix_entree_usd']:>9.2f}"
                  f"{(l.get('cours_usd') or l['prix_entree_usd']):>9.2f}"
                  f"{l['valeur_eur']:>9.2f}{l['pnl_eur']:>+8.2f}{l['pnl_pct']:>+7.2f}%"
                  f"  {l['date_catalyseur']} (J{jc if jc is not None else '?'})")
        print(f"{'Cash':<7}{'' :>8}{'' :>9}{'' :>9}{v['cash_eur']:>9.2f}")
        print(f"{'TOTAL':<7}{'' :>8}{'' :>9}{'' :>9}{v['total_eur']:>9.2f}"
              f"{v['pnl_eur']:>+8.2f}")
        for l in v.get("reelles", []):
            pru = l["montant_declare_eur"] / l["qty"] if l["qty"] else 0.0
            cours = l.get("cours") or l["prix_declaration"]
            devise = "€" if (l.get("devise_cours") == "EUR" or l["devise"] == "EUR") else "$"
            print(f"{l['ticker'] + '*':<7}{l['qty']:>8.4f}{pru:>8.2f}{devise}"
                  f"{cours:>9.2f}{l['valeur_eur']:>9.2f}{l['pnl_eur']:>+8.2f}"
                  f"{l['pnl_pct']:>+7.2f}%  réelle, protégée (CHMP ~2027)")
            print(f"{'PATR. SUIVI':<12}{'' :>4}{'' :>9}{'' :>9}"
                  f"{v['total_eur'] + v['valeur_reelles_eur']:>9.2f}"
                  f"{v['pnl_eur'] + sum(r['pnl_eur'] for r in v['reelles']):>+8.2f}")
        print("* position réelle hors sleeve (MEDCL.PA), jamais vendue automatiquement")
        if alertes:
            print("ALERTES :")
            for a in alertes:
                print(f"  ! {a}")
        else:
            print("Aucune alerte.")
        return

    if args.cmd == "journal":
        for e in etat["journal"][-20:]:
            print(f"{e['date'][:16]} {e['action']:>8} {e.get('ticker', ''):<9} {e.get('eur', '')} EUR")
        return

    v = biotech.valeur(etat, t)
    print(f"Sleeve biotech : {v['total_eur']:.2f} EUR (lignes {v['valeur_lignes_eur']:.2f} "
          f"+ cash {v['cash_eur']:.2f}) | P&L ouvert {v['pnl_eur']:+.2f} EUR | "
          f"taux EUR/USD {t:.4f} | mode {mode}")
    if not v["lignes"]:
        print("Aucune ligne ouverte. Watchlist : data/biotech_watchlist.md")
    for l in v["lignes"]:
        jc = l["jours_catalyseur"]
        jc_txt = f"{jc} j" if jc is not None else "n/d"
        eto = " [eToro demo]" if l.get("etoro", {}).get("compte") == "demo" else \
              (" [eToro REEL]" if l.get("etoro") else "")
        print(f"  {l['ticker']:<6} {l['nom'][:24]:<24} {l['valeur_eur']:>6.2f} EUR "
              f"({l['pnl_pct']:+6.2f} %) | {l['catalyseur']} ({l['date_catalyseur']}, J{jc_txt}){eto}")
    if v.get("reelles"):
        plafonds = cfg.get("etoro", {}).get("protection_positions_reelles", {})
        print(f"Positions reelles declarees : {v['valeur_reelles_eur']:.2f} EUR")
        for l in v["reelles"]:
            prot = plafonds.get(l["ticker"])
            cap = (f", protection {prot['vente_max_eur_cumulee']} EUR "
                   f"(vendu {etat.get('ventes_reelles', {}).get(l['ticker'], 0):.2f})") if prot else ""
            print(f"  {l['ticker']:<9} {l['nom'][:24]:<24} {l['valeur_eur']:>8.2f} EUR "
                  f"({l['pnl_pct']:+6.2f} % depuis declaration){cap}")


if __name__ == "__main__":
    main()
