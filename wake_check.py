"""Check local Survival1K sans fenetre (tache Planificateur, pythonw.exe).

Remplace wake_check.ps1 : aucun console flash ni vol de focus. Throttle 14 min :
la tache tourne toutes les 15 min mais le script ne fait rien si le dernier
check local date de moins de 14 minutes (l'objectif reste le rattrapage au
reveil du PC, pas la surveillance continue pendant l'utilisation).
"""
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
STAMP = BASE / "data" / "wake_check.txt"
RADAR = BASE / "data" / "last_radar.txt"
LOG = BASE / "data" / "wake_checks.log"

maintenant = datetime.now()
# Ne travailler que si c'est VRAIMENT utile : si le radar de l'agent (horaire,
# anti-spam 2h30) est frais, le PC est actif et couvert — sortie immédiate,
# sans réseau. Le check local ne sert qu'au rattrapage (réveil, créneau manqué).
try:
    dernier_radar = datetime.fromisoformat(RADAR.read_text(encoding="utf-8").strip())
    if maintenant - dernier_radar < timedelta(minutes=150):
        sys.exit(0)
except (FileNotFoundError, ValueError):
    pass
if STAMP.exists():
    try:
        dernier = datetime.fromisoformat(STAMP.read_text(encoding="utf-8").strip())
        if maintenant - dernier < timedelta(minutes=14):
            sys.exit(0)
    except ValueError:
        pass
STAMP.write_text(maintenant.isoformat(timespec="seconds"), encoding="utf-8")

debut = datetime.now()
avec_log = open(LOG, "a", encoding="utf-8")
avec_log.write(f"=== CHECK LOCAL {maintenant:%Y-%m-%d %H:%M:%S} ===\n")
try:
    subprocess.run(
        [sys.executable, str(BASE / "bio.py"), "--local", "check"],
        stdout=avec_log, stderr=subprocess.STDOUT,
        cwd=str(BASE), timeout=120,
        creationflags=0x08000000,  # CREATE_NO_WINDOW : aucun flash de console
    )
except Exception as e:
    avec_log.write(f"ERREUR: {e}\n")
finally:
    avec_log.write(f"--- durée : {(datetime.now() - debut).total_seconds():.1f} s\n")
    avec_log.close()

# rotation du log (max ~100 Ko)
try:
    if LOG.exists() and LOG.stat().st_size > 100_000:
        lignes = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        LOG.write_text("\n".join(lignes[-60:]) + "\n", encoding="utf-8")
except Exception:
    pass
