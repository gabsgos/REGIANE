# ABEL Clinica

Modernizacao do sistema local de gestao da clinica medica credenciada pelo DETRAN.

## Estado atual

- Fase 0 concluida: legado inventariado, copiado e restaurado com hashes conferidos.
- Fase 1 concluida localmente: fundacao FastAPI, Poetry, testes e versionamento.
- O envio ao Git remoto depende da configuracao do repositorio remoto.
- Os dados em `ABEL-BAK` sao fonte legada e nao devem ser editados.

## Desenvolvimento

```powershell
poetry install
poetry run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
poetry run pytest
poetry run ruff check backend tests
```

Health check: `http://127.0.0.1:8000/api/health`

## Seguranca

- Nao versionar `.env`, bancos, backups, laudos ou dados clinicos.
- O navegador nunca deve acessar o MySQL diretamente.
- Credenciais antigas nao serao migradas.

