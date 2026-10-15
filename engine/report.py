"""Rapport markdown de l'etat du portefeuille, ecrit dans data/report.md."""
from datetime import datetime, timezone

from . import portfolio as pf


def _position_line(state, prices, asset):
    h = state["holdings"][asset]
    if asset not in prices:
        return f"| {asset} | {h['qty']:.8f} | {h['cost_eur']:.2f} EUR | n/a | n/a | n/a |"
    val = h["qty"] * prices[asset]
    diff = val - h["cost_eur"]
    if abs(diff) < 0.005:  # evite l'affichage "-0.00" du aux arrondis de frais
        diff = 0.0
    line = (val / h["cost_eur"] - 1) * 100 if h["cost_eur"] else 0.0
    return (
        f"| {asset} | {h['qty']:.8f} | {h['cost_eur']:.2f} EUR "
        f"| {val:.2f} EUR | {diff:+.2f} EUR | {line:+.2f} % |"
    )


def build_report(state, cfg, prices, var_7j, drawdown, fg=None, bio=None):
    p = pf.pnl(state, prices)
    regles = cfg["regles"]
    alertes = []
    if drawdown > float(regles["alerte_drawdown_pct"]):
        alertes.append(f"DRAWDOWN {drawdown:.1f}% > seuil d'alerte {regles['alerte_drawdown_pct']}%")
    if var_7j <= float(cfg["crypto"]["dip"]["seuil_pct"]):
        alertes.append(f"Variation 7j ({var_7j:+.1f}%) sous le seuil dip -> renfort envisage")
    fg_txt = f"{fg['valeur']}/100 ({fg['label']})" if fg else "indisponible"

    lignes = [
        f"# Rapport portefeuille - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"- Mode : **{state['mode']}**",
        f"- Valeur sleeve crypto : **{p['total_sleeve']:.2f} EUR** "
        f"(dont crypto {p['valeur_crypto']:.2f} + cash {p['cash']:.2f})",
        f"- Investi : {p['investi']:.2f} EUR | P&L : **{p['pnl_pct']:+.2f} %**",
        f"- Variation 7j sleeve : {var_7j:+.2f} % | Drawdown depuis pic : {drawdown:.2f} %",
        f"- Sentiment (Fear & Greed) : {fg_txt}",
        f"- Progression DCA : {state['dca_done']}/{state['dca_planned']} vagues | "
        f"Reserve dip restante : {state['dip_reserve_eur']:.2f} EUR",
        f"- ETF (manuel, declare) : {pf.etf_total(state):.2f} EUR "
        f"/ {cfg['allocation']['etf_eur']} EUR vises",
        "",
        "## Positions",
        "",
        "| Actif | Quantite | PRU cumule | Valeur | P&L | P&L % |",
        "|---|---|---|---|---|---|",
    ]
    lignes += [_position_line(state, prices, a) for a in state["holdings"]]

    lignes += ["", "## Trades", ""]
    if state["trades"]:
        lignes += ["| Date | Type | Actif | EUR | Prix | Qte |", "|---|---|---|---|---|---|"]
        for t in state["trades"][-15:]:
            lignes.append(
                f"| {t['date'][:16]} | {t['kind']} | {t['asset']} | {t['eur']:.2f} "
                f"| {t['price']:.2f} | {t['qty']:.8f} |"
            )
    else:
        lignes.append("*Aucun trade pour l'instant.*")

    if alertes:
        lignes += ["", "## Alertes", ""]
        lignes += [f"- **{a}**" for a in alertes]

    if bio:
        lignes += [
            "",
            "## Sleeve biotech (catalyseurs FDA/EMA)",
            "",
            f"- Valeur : **{bio['total_eur']:.2f} EUR** "
            f"(lignes {bio['valeur_lignes_eur']:.2f} + cash {bio['cash_eur']:.2f}) | "
            f"P&L ouvert : {bio['pnl_eur']:+.2f} EUR",
            "",
            "| Ticker | Ligne | Valeur | P&L | Catalyseur | J restants |",
            "|---|---|---|---|---|---|",
        ]
        for l in bio["lignes"]:
            jc = l["jours_catalyseur"]
            lignes.append(
                f"| {l['ticker']} | {l['nom'][:24] or '-'} | {l['valeur_eur']:.2f} EUR "
                f"| {l['pnl_eur']:+.2f} EUR ({l['pnl_pct']:+.2f} %) "
                f"| {l['catalyseur']} ({l['date_catalyseur']}) "
                f"| {jc if jc is not None else 'n/d'} |"
            )
        lignes += ["", f"Regles : {cfg['biotech']['regle_sortie']} — "
                      f"stop {cfg['biotech']['stop_loss_pct']}% ; "
                      f"watchlist : `data/biotech_watchlist.md`", ""]
        if bio.get("reelles"):
            lignes += [
                "### Positions reelles declarees (hors sleeve papier)",
                "",
                f"Valeur : **{bio['valeur_reelles_eur']:.2f} EUR**",
                "",
                "| Ticker | Ligne | Valeur | P&L depuis declaration |",
                "|---|---|---|---|",
            ]
            for l in bio["reelles"]:
                lignes.append(
                    f"| {l['ticker']} | {l['nom'][:24] or '-'} | {l['valeur_eur']:.2f} EUR "
                    f"| {l['pnl_eur']:+.2f} EUR ({l['pnl_pct']:+.2f} %) |"
                )
            lignes.append("")

    lignes += [
        "",
        "## Veille info",
        "",
        "Les evenements impactants de la semaine (macro, regulation, flux ETF, adoption) "
        "sont consignes par l'agent dans `data/news.md`, avec leur correlation "
        "a la variation de la sleeve.",
        "",
    ]

    lignes += [
        "",
        "## Prochaines etapes",
        "",
        f"- Prochaine vague DCA : "
        f"{'oui (' + str(cfg['crypto']['dca']['tranche_eur']) + ' EUR)' if state['dca_done'] < state['dca_planned'] else 'phase d entree terminee'}",
        f"- Part ETF : {cfg['etf']['rythme_conseille']} via {cfg['etf']['plateforme']}",
        f"- Vente bloquee jusqu'a : +{regles['vente_bloquee_mois']} mois apres creation "
        f"({state['created_at'][:10]})",
        "",
    ]
    return "\n".join(lignes)


def write_report(state, cfg, prices, var_7j, drawdown, fg=None, bio=None):
    contenu = build_report(state, cfg, prices, var_7j, drawdown, fg, bio)
    pf.DATA.mkdir(exist_ok=True)
    (pf.DATA / "report.md").write_text(contenu, encoding="utf-8")
    return contenu
