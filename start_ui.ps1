param(
    [int]$Port = 8000,
    [string]$BindHost = "127.0.0.1",
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

function Resolve-PythonExecutable {
    param([string]$ProjectRoot)

    $candidates = @()
    if ($env:FACTCHECK_PYTHON) {
        $candidates += $env:FACTCHECK_PYTHON
    }

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $candidates += $venvPython
    }

    if ($env:CONDA_PREFIX) {
        $condaPython = Join-Path $env:CONDA_PREFIX "python.exe"
        if (Test-Path $condaPython) {
            $candidates += $condaPython
        }
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $candidates += $pythonCommand.Source
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return @{ FilePath = $candidate; Arguments = @() }
        }
    }

    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        return @{ FilePath = $pyCommand.Source; Arguments = @("-3") }
    }

    throw "No Python executable found. Activate your environment or set FACTCHECK_PYTHON."
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Resolve-PythonExecutable -ProjectRoot $projectRoot
$serverArgs = @()
$serverArgs += $python.Arguments
$serverArgs += @("-m", "uvicorn", "app.main:app", "--host", $BindHost, "--port", $Port)

Write-Host "Starting NewsFactcheck Agent on http://$BindHost`:$Port/ui" -ForegroundColor Cyan
Write-Host "Project root: $projectRoot"

$process = Start-Process -FilePath $python.FilePath -ArgumentList $serverArgs -WorkingDirectory $projectRoot -PassThru

$baseUrl = "http://$BindHost`:$Port"
$uiUrl = "$baseUrl/ui"
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        Invoke-WebRequest -Uri "$baseUrl/" -TimeoutSec 2 -UseBasicParsing | Out-Null
        $ready = $true
        break
    } catch {
    }
}

if (-not $NoBrowser) {
    Start-Process $uiUrl | Out-Null
}

if ($ready) {
    Write-Host "UI opened: $uiUrl" -ForegroundColor Green
} else {
    Write-Warning "Server is still starting. Browser has been opened to $uiUrl."
}

Write-Host "Server PID: $($process.Id)"
