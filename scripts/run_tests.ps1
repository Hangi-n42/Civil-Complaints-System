param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project virtual environment not found: $Python"
}

if (-not $PytestArgs) {
    $PytestArgs = @("app/tests")
}

# The workspace may be on a synchronized drive where __pycache__ is read-only.
$env:PYTHONDONTWRITEBYTECODE = "1"

Push-Location $ProjectRoot
try {
    & $Python -m pytest -p no:cacheprovider @PytestArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
