param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$runner = Join-Path $PSScriptRoot "run_in_rag_crm.ps1"
$arguments = @("tools/golden_match_regression.py") + ($ExtraArgs | Where-Object { $_ -ne $null })

& $runner @arguments
exit $LASTEXITCODE
