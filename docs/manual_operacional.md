# Manual operacional ABEL

## Inicialização

1. Confirme o MySQL em `127.0.0.1:3307`.
2. No diretório do projeto, execute `poetry install`.
3. Aplique o schema com `poetry run alembic upgrade head`.
4. Inicie com `poetry run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`.
5. Abra `http://127.0.0.1:8000` e confirme `/api/health` com todos os checks `ok`.

## Credencial inicial

A credencial do administrador está em `data/initial-admin.secret`, com ACL
restrita. No primeiro login, troque a senha. Nunca copie esse arquivo para logs,
mensagens ou mídia não criptografada.

## Backup

A tarefa `ABEL Backup Diario` executa diariamente às 22:00 e também inicia assim
que possível após uma execução perdida. O comando manual é:

`powershell -NoProfile -File tools/run_backup.ps1`

O resultado fica em `backups/system/*.abelbak`, autenticado e criptografado com
AES-256-GCM. A chave derivada está em `data/backup.passphrase`, separada do
backup e com ACL restrita. São mantidos os 14 backups mais recentes.

## Verificações diárias

- `/api/health`: API, banco e armazenamento devem estar `ok`.
- `data/logs/abel.jsonl`: buscar `level=ERROR` sem copiar dados sensíveis.
- Conferir o horário e o tamanho do último `.abelbak`.
- Conferir a tarefa agendada em estado `Ready`.

## Encerramento

Pare o Uvicorn de forma controlada. Não encerre o MySQL durante uma gravação,
backup ou migração. O sistema legado somente deverá permanecer em modo leitura
depois do corte formalmente homologado; antes disso, seu estado não deve ser
alterado por estes procedimentos.
