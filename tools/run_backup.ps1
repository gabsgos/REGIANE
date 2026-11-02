$ErrorActionPreference = "Stop"
Set-Location -LiteralPath "C:\Users\gabri\Documents\ABEL"
& "C:\Program Files\Python311\Scripts\poetry.exe" run python -m tools.backup_system
exit $LASTEXITCODE
