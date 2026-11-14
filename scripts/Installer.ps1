$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)

try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if (-not $launcher) { throw 'Installez Python 3.12 x64 depuis python.org avec le lanceur py.' }
        & $launcher.Source -3.12 -c "import struct, sys; sys.exit(struct.calcsize('P') != 8)"
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 x64 est requis.' }
        & $launcher.Source -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Creation de l'environnement Python impossible." }
    }

    $python = '.venv\Scripts\python.exe'
    & $python -m pip --disable-pip-version-check install --use-feature=truststore -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Installation incomplete. Verifiez la connexion puis relancez Installer.cmd.' }
    & $python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Les dependances Python sont incompatibles.' }

    $ollama = Get-Command ollama.exe -ErrorAction SilentlyContinue
    $installed = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (-not $ollama -and -not (Test-Path $installed) -and -not (Test-Path '.runtime\ollama\ollama.exe')) {
        Write-Host 'Installez Ollama depuis https://ollama.com/download/windows pour activer le modele local.'
    }
    Write-Host 'Application installee. Modele par defaut : ollama pull qwen3:8b. Puis double-cliquez sur Lancer.cmd.'
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
