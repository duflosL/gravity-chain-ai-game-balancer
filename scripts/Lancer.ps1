$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
$root = (Get-Location).Path
$runtime = Join-Path $root '.runtime'
$python = '.venv\Scripts\python.exe'
$port = if ($env:GC_BALANCER_PORT) { [int]$env:GC_BALANCER_PORT } else { 8765 }
$appUrl = "http://127.0.0.1:$port"
$localFile = Join-Path $runtime 'local-settings.json'
$local = if (Test-Path -LiteralPath $localFile) { Get-Content -Raw -LiteralPath $localFile | ConvertFrom-Json } else { $null }
if ($local.python -and (Test-Path -LiteralPath $local.python)) { $python = $local.python }
if ($env:GC_BALANCER_PYTHON) { $python = $env:GC_BALANCER_PYTHON }
$ownedOllama = $null
$browserHelper = $null

try {
    if (-not (Test-Path -LiteralPath $python)) { throw "Lancez d'abord Installer.cmd." }
    & $python -c 'import streamlit, plotly, pandas, numpy'
    if ($LASTEXITCODE -ne 0) { throw 'Dependances incompletes. Relancez Installer.cmd.' }
    $portBusy = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($portBusy) { throw "Le port $port est deja utilise. Fermez le lanceur precedent ou configurez GC_BALANCER_PORT." }

    try {
        Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2 | Out-Null
    } catch {
        $portable = if ($local.ollama) { $local.ollama } else { Join-Path $runtime 'ollama\ollama.exe' }
        if (Test-Path -LiteralPath $portable) {
            $env:OLLAMA_HOST = '127.0.0.1:11434'
            $env:OLLAMA_MODELS = if ($local.models) { $local.models } else { Join-Path $runtime 'models' }
            $env:OLLAMA_NO_CLOUD = '1'
            $env:OLLAMA_NUM_PARALLEL = '1'
            if ($local.disableVulkan) { $env:OLLAMA_VULKAN = '0' }
            $ownedOllama = Start-Process -FilePath $portable -ArgumentList 'serve' -PassThru -WindowStyle Hidden `
                -RedirectStandardOutput (Join-Path $runtime 'ollama.out.log') `
                -RedirectStandardError (Join-Path $runtime 'ollama.err.log')
        } else {
            Write-Host "Ollama est indisponible. L'analyse CSV reste utilisable. Demarrez Ollama pour activer l'agent."
        }
    }

    if (-not $env:GC_BALANCER_NO_BROWSER) {
        $browserHelper = Start-Job -ArgumentList $appUrl -ScriptBlock {
            param($url)
            for ($i = 0; $i -lt 25; $i++) {
                try {
                    Invoke-RestMethod "$url/_stcore/health" -TimeoutSec 1 | Out-Null
                    Start-Process $url
                    break
                } catch {
                    Start-Sleep -Milliseconds 400
                }
            }
        }
    }
    Write-Host "Gravity Chain AI Game Balancer : $appUrl"
    Write-Host "Laissez cette fenetre ouverte pendant l'utilisation. Ctrl+C pour arreter."
    & $python -m streamlit run app.py --server.port $port
    if ($LASTEXITCODE -ne 0) { throw "Le lancement de l'application a echoue." }
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
} finally {
    if ($browserHelper) { Remove-Job -Job $browserHelper -Force -ErrorAction SilentlyContinue }
    if ($ownedOllama -and -not $ownedOllama.HasExited) {
        Stop-Process -Id $ownedOllama.Id -ErrorAction SilentlyContinue
    }
}
