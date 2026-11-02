# Recuperação de desastre

## Pré-requisitos

- Arquivo `.abelbak` íntegro.
- `data/backup.passphrase` correspondente, armazenado separadamente.
- MySQL 8.4 e Poetry disponíveis.
- Espaço livre superior ao dobro do dump descompactado.

## Ensaio seguro

Execute `poetry run python -m tools.restore_backup_test`. A rotina:

1. autentica e descriptografa o arquivo;
2. valida caminhos e SHA-256 do dump;
3. cria `abel_restore_test` vazio;
4. restaura todas as tabelas;
5. compara contagens e hashes dos documentos;
6. remove exclusivamente o banco de ensaio.

Nunca aponte esse ensaio para `abel_clinica`.

## Recuperação de produção

1. Interrompa a API e preserve o banco danificado sem sobrescrevê-lo.
2. Copie o último backup e a chave para mídia local controlada.
3. Execute primeiro o ensaio isolado e confirme `integrity=PASS`.
4. Crie um banco novo, restaure o SQL e valide as mesmas contagens.
5. Restaure documentos no diretório privado e confira todos os hashes.
6. Atualize `.env` somente após validação, aplique Alembic e inicie a API.
7. Execute login, cadastro, pagamento, recibo, laudo e relatórios de fumaça.
8. Mantenha o banco anterior intacto até aprovação formal.

## Evidência atual

O backup de Fase 12 restaurou 20 tabelas e 342.739 linhas em banco isolado. O
dump, todas as contagens e todos os hashes de documentos coincidiram. O banco de
ensaio foi removido após a prova.
