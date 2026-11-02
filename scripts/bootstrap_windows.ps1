# Download an isolated runtime and stage source locally, including from UNC shares.
# No administrator access or system Python/PATH changes are requested.
$ErrorActionPreference = 'Stop'
try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw '64-bit Windows is required.' }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $source = Split-Path -Parent $PSScriptRoot
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $id = ([BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($source.ToLowerInvariant())))).Replace('-', '').Substring(0, 12) }
    finally { $hasher.Dispose() }
    $cache = Join-Path $env:LOCALAPPDATA "GroundAndLaw\$id"
    $app = Join-Path $cache 'app'
    $tools = Join-Path $cache 'tools'
    New-Item -ItemType Directory -Force -Path $app, $tools | Out-Null
    Write-Host "Preparing local app: $app"
    foreach ($directory in @('land_assistant', 'groundAndLaw', 'knowledge', 'scripts', 'examples')) {
        $from = Join-Path $source $directory
        $to = Join-Path $app $directory
        & robocopy $from $to /E /XD __pycache__ /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "Could not copy $directory from project folder." }
    }
    foreach ($file in @('requirements-legal.txt', 'requirements-speech.txt', '.env.example')) {
        Copy-Item -LiteralPath (Join-Path $source $file) -Destination (Join-Path $app $file) -Force
    }
    $envFile = Join-Path $app '.env'
    if (Test-Path -LiteralPath (Join-Path $source '.env')) {
        Copy-Item -LiteralPath (Join-Path $source '.env') -Destination $envFile -Force
    } elseif (-not (Test-Path -LiteralPath $envFile)) {
        Copy-Item -LiteralPath (Join-Path $app '.env.example') -Destination $envFile

    }
    if ($args -notcontains '--demo') {
        $contents = Get-Content -LiteralPath $envFile -Raw
        $needsConfig = $false
        foreach ($key in @('LLM_URL', 'LLM_API_KEY', 'LLM_MODEL')) {
            $match = [regex]::Match($contents, ('(?m)^\s*' + $key + '\s*=\s*([^\r\n]*)'))
            if (-not $match.Success -or -not $match.Groups[1].Value.Trim().Trim([char]34).Trim([char]39)) { $needsConfig = $true }
        }
        if ($needsConfig) {
            Write-Host 'Fill LLM_URL, LLM_API_KEY and LLM_MODEL, then save and close Notepad.'
            Start-Process notepad.exe -ArgumentList @('"' + $envFile + '"') -Wait
        }
    }
    $uv = Join-Path $tools 'uv.exe'
    $uvHash = 'a2a8820d5eea32f08ef467ef3b7f66883a9b076d5737a2fc2fbb5f458d1bb50f'
    # Fixed upstream release, ZIP checked against the upstream SHA-256 digest.
    if (-not (Test-Path -LiteralPath $uv)) {
        Write-Host 'Downloading portable runtime manager...'
        $archive = Join-Path $tools 'uv-download.zip'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/astral-sh/uv/releases/download/0.13.6/uv-x86_64-pc-windows-msvc.zip' -OutFile $archive
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $uvHash) {
            Remove-Item -LiteralPath $archive -Force
            throw 'Runtime download checksum mismatch. Download was not executed.'
        }
        Expand-Archive -LiteralPath $archive -DestinationPath $tools -Force
        $binary = Get-ChildItem -LiteralPath $tools -Filter uv.exe -Recurse | Select-Object -First 1
        if (-not $binary) { throw 'Runtime manager was not found in the verified archive.' }
        if ($binary.FullName -ne $uv) { Copy-Item -LiteralPath $binary.FullName -Destination $uv -Force }
        Remove-Item -LiteralPath $archive -Force
    }
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $cache 'python'
    $env:UV_PYTHON_BIN_DIR = Join-Path $cache 'python-bin'
    $env:UV_CACHE_DIR = Join-Path $cache 'uv-cache'
    Write-Host 'Preparing Python 3.12 (downloaded only when missing)...'
    & $uv python install 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare Python. Check Internet access and organization policies.' }
    $python = & $uv python find --managed-python 3.12
    if ($LASTEXITCODE -ne 0 -or -not $python) { throw 'Managed Python 3.12 was not found.' }
    Set-Location -LiteralPath $app
    & $python scripts/run_web.py --auto-port @args
    exit $LASTEXITCODE
} catch {
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
