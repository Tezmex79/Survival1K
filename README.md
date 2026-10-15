# 100 Survival — Système d'investissement automatisé sur eToro

Réponse à la question : *« Si je te donnais 100 € et que tu devais investir pour survivre,
comment le ferais-tu ? »* — un système **simulé d'abord**, discipliné, piloté par données
réelles, automatisé par un agent ZCode (tâches planifiées), conçu pour s'exécuter sur
**eToro** (le broker de l'utilisateur, compte vérifié, API publique disponible).

## La stratégie en une phrase

Un socle prudent en ETF monde (60 €) + une sleeve spéculative **actions biotech à
catalyseurs réglementaires FDA/EMA** (40 €) gérée en micro-positions disciplinées —
la volatilité binaire y est maximale, la taille des lignes est le contrôleur de risque.

## Allocation des 100 € (100 % eToro)

| Part | Montant | Support eToro | Frais | Mode |
|---|---|---|---|---|
| ETF | 60 € | ETF MSCI World (0 commission, fractions dès ~10 $) | 0 % | Manuel, 20 € × 3 semaines, déclaré via `--etf` |
| Biotech | 200 € | Lignes événementielles FDA/EMA, 20 € max chacune, 10 max | 0 % | Automatisé : simulation → démo eToro → réel eToro |
| Crypto | 0 € | *(en sommeil, moteur conservé et réactivable via config)* | 1 % | — |

> Financement en réel (instruction utilisateur du 15/10/2026) : la sleeve biotech de
> 200 € sera financée par la vente de 200 € de la position réelle Medincell, au
> moment du basculement en réel et sur instruction explicite.

### Règles biotech (`config.yaml > biotech`)
- **Screening hebdo** (agent, sourcé) : catalyseur FDA (PDUFA/AdComm) ou EMA (CHMP)
  daté dans les 2-8 semaines, capitalisation > 300 M$, disponible sur eToro
- **Micro-positions** : 10 € max par ligne (minimum eToro ~10 $) — un refus réglementaire
  à -60 % coûte 6 €, soit 6 % du capital total
- **Sortie systématique** après résolution du catalyseur (approbation OU refus) :
  l'événement est prix dans le titre, on ne s'attache pas (« sell the news » existe)
- **Stop-loss -30 %** si la ligne décroche avant l'événement
- Watchlist sourcée : `data/biotech_watchlist.md` · portefeuille : `data/biotech.json`

### Règles crypto (dormantes, réactivables)
DCA 3×10 € + réserve dip 10 € déclenchée à -12 %/7 j ; le moteur et le backtest
3 ans restent dans le repo (`backtest.py`), il suffit de repasser
`crypto.actif: true` et `allocation.crypto_eur: 40`.

## Backtest crypto 3 ans (référence, frais eToro 1 % — la sleeve biotech, elle,
ne se backteste pas : les catalyseurs passés ne se rejouent pas)

| Stratégie | Médiane | Moyenne | Pire cas |
|---|---|---|---|
| Lump sum | +1,46 % | +3,08 % | -38,26 % |
| DCA pur | +0,29 % | +1,89 % | -26,34 % |
| DCA + dip -12 % | +1,97 % | +2,15 % | -26,34 % |

## Utilisation

```bash
.venv/Scripts/python run_dca.py             # tick global (crypto/ETF/sentiment/rapport)
.venv/Scripts/python run_dca.py --etf 20    # déclarer un achat ETF manuel de 20 €
.venv/Scripts/python bio.py                 # statut sleeve biotech
.venv/Scripts/python bio.py buy BBIO 10 "PDUFA BBP-418" 2026-11-27 --nom "BridgeBio"
.venv/Scripts/python bio.py sell BBIO "catalyseur résolu"
.venv/Scripts/python bio.py journal         # historique des opérations
.venv/Scripts/python backtest.py            # backtest crypto (référence)
```

Modes (`mode:` dans `config.yaml`) : `simulation` (défaut) · `etoro-demo` (ordres sur
compte démo) · `etoro-real` (**dry-run** sauf flag `--execute` — double sécurité).

## Passer sur eToro (démo d'abord, puis réel)

1. **Clés API** (compte vérifié) : eToro → Paramètres → Trading → Gestion des clés API →
   créer une clé ; copier la **user key immédiatement** (affichée une seule fois).
   Docs : https://api-portal.etoro.com — l'API ne permet **aucun retrait de fonds**
2. `cp .env.example .env` + renseigner `ETORO_API_KEY` / `ETORO_USER_KEY`
3. `mode: etoro-demo` → 2-3 lundis de vérification, puis `mode: etoro-real`
4. Avant tout achat réel biotech : vérifier que le titre est bien proposé sur eToro
   (sinon fallback : ETF XBT/XBI, disponible eToro, pour l'exposition biotech)

## Automatisation par l'agent ZCode — radar 4×/jour en semaine

L'automatisation tourne **lundi au vendredi, à 8 h / 13 h / 17 h / 21 h**
(couverture pré-market US, ouverture, séance, after-heures) :

- **À chaque créneau (radar)** : `bio.py check` → stop-loss -30 % ou catalyseur échu
  déclenchent une action immédiate (vente, recherche de l'issue, archivage) ;
  veille news rapide par ticker détenu ; réponse 1 ligne si tout va bien
- **Lundi 8 h en plus** : tick global (`run_dca.py`, sans `--execute`) + Fear & Greed,
  screening FDA/EMA complet de la semaine, achat papier 10 € si un candidat qualifie,
  veille macro dans `data/news.md`, résumé hebdo
- **1er lundi du mois** : rapport consolidé des trois sleeves

Réactivité : latence maximale ~4 h en semaine ; un événement du week-end est traité
au radar du lundi 8 h (ou immédiatement sur demande dans la conversation — le chat
prime toujours sur le planning). Les week-ends ne sont pas couverts par défaut car
les annonces FDA/CHMP y sont rares ; demander à étendre si besoin.

## Avertissements

Les biotechs à catalyseurs sont **binaires** : -50 à -80 % en une séance sur un refus
est courant ; les dates PDUFA déjà étendues ont un taux d'approbation inférieur à la
moyenne ; « sell the news » peut faire baisser le titre même après une approbation.
La taille des lignes (10 €) est LE contrôle du risque — ne jamais l'augmenter sous
émotion. Simulation à but éducatif, aucun rendement garanti, pas un conseil financier.
