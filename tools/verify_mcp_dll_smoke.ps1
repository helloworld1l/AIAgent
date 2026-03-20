param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$runner = Join-Path $PSScriptRoot "run_in_rag_crm.ps1"
$arguments = @("tools/mcp_dll_smoke_regression.py") + ($ExtraArgs | Where-Object { $_ -ne $null })

& $runner @arguments
exit $LASTEXITCODE
