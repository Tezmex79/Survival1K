# Survival1K - check local au reveil du PC (tache Planificateur, toutes les 15 min,
# StartWhenAvailable : la premiere occurrence manquee pendant la veille s'execute
# des le reveil). Throttle : ne fait rien si le dernier check local date de <10 min.
Set-Location "C:\Users\cthezard\DEV\invest"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$stampFile = "data\wake_check.txt"
$now = Get-Date
if (Test-Path $stampFile) {
    $last = Get-Content $stampFile -ErrorAction SilentlyContinue
    $lastDt = [datetime]::MinValue
    if ([datetime]::TryParse($last, [ref]$lastDt) -and ($now - $lastDt).TotalMinutes -lt 10) { exit 0 }
}
Set-Content -Path $stampFile -Value $now.ToString("yyyy-MM-ddTHH:mm:ss")
Add-Content -Path "data\wake_checks.log" -Value "=== CHECK LOCAL $($now.ToString('yyyy-MM-dd HH:mm:ss')) ==="
try {
    & ".venv\Scripts\python.exe" bio.py --local check 2>&1 | Add-Content -Path "data\wake_checks.log"
    # rotation du log (max ~100 Ko)
    $log = Get-Item "data\wake_checks.log" -ErrorAction SilentlyContinue
    if ($log -and $log.Length -gt 100KB) {
        Get-Content $log -Tail 60 | Set-Content $log
    }
} catch {
    Add-Content -Path "data\wake_checks.log" -Value "ERREUR: $($_.Exception.Message)"
}
