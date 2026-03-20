param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PythonArgs
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$candidatePaths = New-Object System.Collections.Generic.List[string]

if ($env:RAG_CRM_PYTHON) {
    $candidatePaths.Add($env:RAG_CRM_PYTHON)
}

$defaultCandidates = @(
    (Join-Path $env:USERPROFILE ".conda\envs\rag_crm\python.exe"),
    "C:\Users\$env:USERNAME\.conda\envs\rag_crm\python.exe",
    "D:\ProgramData\anaconda3\envs\rag_crm\python.exe"
)

foreach ($candidate in $defaultCandidates) {
    if ($candidate) {
        $candidatePaths.Add($candidate)
    }
}

$environmentFiles = @(
    (Join-Path $env:USERPROFILE ".conda\environments.txt"),
    (Join-Path $env:USERPROFILE ".anaconda\environments.txt")
)

foreach ($environmentFile in $environmentFiles) {
    if (-not (Test-Path $environmentFile)) {
        continue
    }

    foreach ($line in Get-Content $environmentFile) {
        $environmentPath = $line.Trim()
        if (-not $environmentPath) {
            continue
        }
        if ((Split-Path $environmentPath -Leaf) -ne "rag_crm") {
            continue
        }
        $candidatePaths.Add((Join-Path $environmentPath "python.exe"))
    }
}

$pythonExe = $candidatePaths |
    Where-Object { $_ -and (Test-Path $_) } |
    Select-Object -Unique |
    Select-Object -First 1

if (-not $pythonExe) {
    throw "Unable to locate rag_crm Python. Set RAG_CRM_PYTHON or install the rag_crm conda environment."
}

$resolvedArgs = @()
foreach ($arg in ($PythonArgs | Where-Object { $_ -ne $null })) {
    if ($arg.StartsWith("-")) {
        $resolvedArgs += $arg
        continue
    }

    $repoRelativePath = Join-Path $repoRoot $arg
    if (Test-Path $repoRelativePath) {
        $resolvedArgs += (Resolve-Path $repoRelativePath).Path
        continue
    }

    $resolvedArgs += $arg
}

if (-not $resolvedArgs) {
    $resolvedArgs = @((Join-Path $repoRoot "main.py"))
}

& $pythonExe @resolvedArgs
exit $LASTEXITCODE
