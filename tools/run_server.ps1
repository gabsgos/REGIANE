$ErrorActionPreference = "Stop"
Set-Location -LiteralPath "C:\Users\gabri\Documents\ABEL"
& "C:\Program Files\Python311\Scripts\poetry.exe" run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
