param(
    [string[]]$Providers = @("all"),
    [string]$Manifest = "",
    [switch]$SkipFetch,
    [switch]$SkipIndex
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

    $tail = Get-Content -LiteralPath $Path -Tail 25 -ErrorAction SilentlyContinue
    if ($tail) {
        Write-Host "---- $Path ----" -ForegroundColor Yellow
        $tail | ForEach-Object { Write-Host $_ }
    }
}

function Test-PythonCandidate {
    param(
        [pscustomobject]$Candidate,
        [string]$ProjectRoot
    )

    $env:PYTHONPATH = "."
    $probeArgs = @()
    $probeArgs += $Candidate.Arguments
    $probeArgs += @(
        "-c",
        "import qdrant_client, langchain_openai, dotenv; print('ok')"
    )

    try {
        $output = & $Candidate.FilePath @probeArgs 2>$null
        return ($LASTEXITCODE -eq 0 -and ($output -match "ok"))
    } catch {
        return $false
    }
}

function Invoke-Step {
    param(
        [pscustomobject]$Candidate,
        [string]$ProjectRoot,
        [string[]]$ScriptArgs,
        [string]$StdoutLog,
        [string]$StderrLog,
        [string]$Label
    )

    $env:PYTHONPATH = "."
    $allArgs = @()
    $allArgs += $Candidate.Arguments
    $allArgs += $ScriptArgs

    Add-Content -LiteralPath $StdoutLog -Value "== $Label =="
    Add-Content -LiteralPath $StderrLog -Value "== $Label =="

    $process = Start-Process `
        -FilePath $Candidate.FilePath `
        -ArgumentList $allArgs `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog `
        -PassThru `
        -Wait

    return ($process.ExitCode -eq 0)
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $projectRoot "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stdoutLog = Join-Path $logDir "open-rag-bootstrap.out.log"
$stderrLog = Join-Path $logDir "open-rag-bootstrap.err.log"

Set-Content -LiteralPath $stdoutLog -Value ""
Set-Content -LiteralPath $stderrLog -Value ""

Write-Host "Bootstrapping open RAG corpus" -ForegroundColor Cyan
Write-Host "Project root: $projectRoot"

$candidates = Get-PythonCandidates -ProjectRoot $projectRoot
if (-not $candidates -or $candidates.Count -eq 0) {
    throw "No Python executable candidates found. Set FACTCHECK_PYTHON or create .venv."
}

$providerArgs = @()
foreach ($provider in $Providers) {
    if ($provider) {
        $providerArgs += $provider
    }
}
if (-not $providerArgs) {
    $providerArgs = @("all")
}

$errors = @()
foreach ($candidate in $candidates) {
    $argText = if ($candidate.Arguments.Count -gt 0) { " $($candidate.Arguments -join ' ')" } else { "" }
    Write-Host "Trying Python: $($candidate.FilePath)$argText" -ForegroundColor DarkCyan

    if (-not (Test-PythonCandidate -Candidate $candidate -ProjectRoot $projectRoot)) {
        Write-Host "Skipping interpreter without required dependencies." -ForegroundColor DarkYellow
        $errors += "$($candidate.FilePath)$argText"
        continue
    }

    $ok = $true
    if (-not $SkipFetch) {
        $fetchArgs = @("scripts\fetch_open_corpus.py", "--providers") + $providerArgs
        if ($Manifest) {
            $fetchArgs += @("--manifest", $Manifest)
        }
        Write-Host "Step 1/2: fetch open corpus" -ForegroundColor Gray
        $ok = Invoke-Step `
            -Candidate $candidate `
            -ProjectRoot $projectRoot `
            -ScriptArgs $fetchArgs `
            -StdoutLog $stdoutLog `
            -StderrLog $stderrLog `
            -Label "fetch_open_corpus"
    }

    if ($ok -and -not $SkipIndex) {
        Write-Host "Step 2/2: rebuild local RAG index" -ForegroundColor Gray
        $ok = Invoke-Step `
            -Candidate $candidate `
            -ProjectRoot $projectRoot `
            -ScriptArgs @("scripts\build_rag_index.py", "--recreate") `
            -StdoutLog $stdoutLog `
            -StderrLog $stderrLog `
            -Label "build_rag_index"
    }

    if ($ok) {
        Write-Host "Open corpus bootstrap completed." -ForegroundColor Green
        Write-Host "Logs: $stdoutLog"
        return
    }

    $errors += "$($candidate.FilePath)$argText"
}

Write-Error "Open corpus bootstrap failed."
Write-Host "Tried interpreters:"
$errors | ForEach-Object { Write-Host "  $_" }
Write-Host "Stdout log: $stdoutLog"
Write-Host "Stderr log: $stderrLog"
Show-LogTail -Path $stdoutLog
Show-LogTail -Path $stderrLog
exit 1
