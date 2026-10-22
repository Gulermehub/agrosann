$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $pythonExe)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        Write-Host 'Instale Python 3.12 ou superior e execute este arquivo novamente.'
        exit 1
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $pythonExe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& $pythonExe -c "from app import app; from agrosan.db import initialize; ctx=app.app_context(); ctx.push(); initialize() if not app.config['DATABASE_URL'] else None"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $pythonExe -c "from app import app; from agrosan.db import get_db; ctx=app.app_context(); ctx.push(); print('Contas cadastradas:', get_db().execute('SELECT COUNT(*) AS n FROM usuarios').fetchone()['n'])"
Write-Host 'Na tela de entrada, clique em Criar minha conta. Em uma instalação vazia, a primeira conta será administradora.'
Write-Host 'AgroSan: http://127.0.0.1:5001 (Ctrl+C para encerrar)'
& (Join-Path $PSScriptRoot '.venv/Scripts/waitress-serve.exe') --listen=127.0.0.1:5001 app:app
