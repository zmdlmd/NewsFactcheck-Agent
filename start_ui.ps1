param(
    [int]$Port = 8000,
    [string]$BindHost = "127.0.0.1",
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

function Add-PythonCandidate {
    param(
        [System.Collections.Generic.List[object]]$Candidates,
        [string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$Label = ""
    )

    if (-not $FilePath) {
        return
    }

    if (-not (Test-Path $FilePath)) {
        return
    }

    foreach ($candidate in $Candidates) {
        if ($candidate.FilePath -eq $FilePath -and (@($candidate.Arguments) -join " ") -eq (@($Arguments) -join " ")) {
            return
        }
    }

    $Candidates.Add([pscustomobject]@{
        FilePath = $FilePath
        Arguments = @($Arguments)
        Label = $Label
    }) | Out-Null
}

function Get-PythonCandidates {
    param([string]$ProjectRoot)

    $candidates = New-Object 'System.Collections.Generic.List[object]'

    Add-PythonCandidate -Candidates $candidates -FilePath $env:FACTCHECK_PYTHON -Label "FACTCHECK_PYTHON"

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    Add-PythonCandidate -Candidates $candidates -FilePath $venvPython -Label ".venv"

    if ($env:CONDA_PREFIX) {
        $condaPython = Join-Path $env:CONDA_PREFIX "python.exe"
        Add-PythonCandidate -Candidates $candidates -FilePath $condaPython -Label "CONDA_PREFIX"
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        Add-PythonCandidate -Candidates $candidates -FilePath $pythonCommand.Source -Label "python"
    }

    $wherePython = & where.exe python 2>$null
    foreach ($path in $wherePython) {
        Add-PythonCandidate -Candidates $candidates -FilePath $path -Label "where python"
    }

    $condaEnvRoot = Join-Path $env:USERPROFILE ".conda\envs"
    if (Test-Path $condaEnvRoot) {
        Get-ChildItem -Path $condaEnvRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            Add-PythonCandidate -Candidates $candidates -FilePath (Join-Path $_.FullName "python.exe") -Label ".conda\envs"
        }
    }

    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        Add-PythonCandidate -Candidates $candidates -FilePath $pyCommand.Source -Arguments @("-3") -Label "py -3"
    }

    return $candidates
}

function Show-LogTail {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    $tail = Get-Content -LiteralPath $Path -Tail 20 -ErrorAction SilentlyContinue
    if ($tail) {
        Write-Host "---- $Path ----" -ForegroundColor Yellow
        $tail | ForEach-Object { Write-Host $_ }
    }
}

function Start-ServerAttempt {
    param(
        [pscustomobject]$Candidate,
        [string]$ProjectRoot,
        [string]$BindHost,
        [int]$Port,
        [string]$StdoutLog,
        [string]$StderrLog
    )

    $serverArgs = @()
    $serverArgs += $Candidate.Arguments
    $serverArgs += @("-m", "uvicorn", "app.main:app", "--host", $BindHost, "--port", $Port)

    Set-Content -LiteralPath $StdoutLog -Value ""
    Set-Content -LiteralPath $StderrLog -Value ""

    $process = Start-Process `
        -FilePath $Candidate.FilePath `
        -ArgumentList $serverArgs `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog `
        -PassThru

    $baseUrl = "http://$BindHost`:$Port"
    for ($i = 0; $i -lt 12; $i++) {
        Start-Sleep -Seconds 1
        if ($process.HasExited) {
            return @{ Ready = $false; Process = $process }
        }

        try {
            Invoke-WebRequest -Uri "$baseUrl/" -TimeoutSec 2 -UseBasicParsing | Out-Null
            return @{ Ready = $true; Process = $process }
        } catch {
        }
    }

    return @{ Ready = $false; Process = $process }
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $projectRoot "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stdoutLog = Join-Path $logDir "ui-server.out.log"
$stderrLog = Join-Path $logDir "ui-server.err.log"

$baseUrl = "http://$BindHost`:$Port"
$uiUrl = "$baseUrl/ui"

Write-Host "Starting NewsFactcheck Agent on $uiUrl" -ForegroundColor Cyan
Write-Host "Project root: $projectRoot"

$candidates = Get-PythonCandidates -ProjectRoot $projectRoot
if (-not $candidates -or $candidates.Count -eq 0) {
    throw "No Python executable candidates found. Set FACTCHECK_PYTHON or create .venv."
}

$errors = @()
foreach ($candidate in $candidates) {
    $argText = if ($candidate.Arguments.Count -gt 0) { " $($candidate.Arguments -join ' ')" } else { "" }
    Write-Host "Trying Python: $($candidate.FilePath)$argText" -ForegroundColor DarkCyan

    $attempt = Start-ServerAttempt `
        -Candidate $candidate `
        -ProjectRoot $projectRoot `
        -BindHost $BindHost `
        -Port $Port `
        -StdoutLog $stdoutLog `
        -StderrLog $stderrLog

    if ($attempt.Ready) {
        if (-not $NoBrowser) {
            Start-Process $uiUrl | Out-Null
        }
        Write-Host "UI opened: $uiUrl" -ForegroundColor Green
        Write-Host "Server PID: $($attempt.Process.Id)"
        Write-Host "Logs: $stdoutLog"
        return
    }

    $errors += "$($candidate.FilePath)$argText"
    if (-not $attempt.Process.HasExited) {
        try {
            Stop-Process -Id $attempt.Process.Id -Force -ErrorAction SilentlyContinue
        } catch {
        }
    }
}

Write-Error "Server failed to start or did not become reachable at $uiUrl"
Write-Host "Tried interpreters:"
$errors | ForEach-Object { Write-Host "  $_" }
Write-Host "Stdout log: $stdoutLog"
Write-Host "Stderr log: $stderrLog"
Show-LogTail -Path $stdoutLog
Show-LogTail -Path $stderrLog
exit 1
