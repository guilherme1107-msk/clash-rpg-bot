$ErrorActionPreference = 'SilentlyContinue'

# Pede primeiro à Central que finalize somente o processo do bot que ela iniciou.
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8765/api/bot/stop' -ContentType 'application/json' -Body '{}' | Out-Null
Start-Sleep -Milliseconds 600

# Encerra somente os processos que estão ouvindo nas portas conhecidas do projeto.
$clashBotPorts = @(8780, 8765)
foreach ($clashBotPort in $clashBotPorts) {
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $clashBotPort
    foreach ($listener in $listeners) {
        if ($listener.OwningProcess -gt 0) {
            Stop-Process -Id $listener.OwningProcess
        }
    }
}

Write-Host 'ClashBot, Activity e Central foram desligados.' -ForegroundColor Green
