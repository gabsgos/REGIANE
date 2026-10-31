# Fase 0 - Topologia e politica operacional

Data da decisao: 2026-10-31

## Topologia inicial

- A estacao Windows local hospeda o ambiente de desenvolvimento.
- O MySQL 8.4 LTS com InnoDB sera o banco principal.
- FastAPI e MySQL serao executados na mesma maquina durante desenvolvimento e homologacao inicial.
- O navegador acessara somente a API; nunca acessara o banco diretamente.
- A exposicao para outros computadores da clinica dependera de validacao posterior de IP fixo, firewall, energia, backup externo e disponibilidade da maquina.
- SQLite fica restrito a testes isolados e nao sera o banco de producao multiusuario.

## Preservacao do legado

- `ABEL-BAK` e a fonte original e deve permanecer somente para leitura durante o desenvolvimento.
- Importadores devem trabalhar sobre copia temporaria verificada.
- Arquivos CDX nao serao migrados como indices; os indices serao reconstruidos no MySQL.
- Arquivos RAR serao preservados como objetos opacos ate que a senha seja fornecida.

## Retencao proposta

- 7 backups diarios.
- 4 backups semanais.
- 12 backups mensais.
- 1 copia final imutavel do legado antes do corte.
- Pelo menos uma copia deve ficar fora da maquina principal.

## Criptografia

- Backups contendo dados clinicos nao devem ser enviados ou copiados para outra maquina sem criptografia.
- A chave ou senha de backup deve ficar separada do arquivo e fora do repositorio Git.
- O ZIP criado na Fase 0 e uma copia local temporaria de validacao; nao esta autorizado para transferencia externa.
- Antes da homologacao deve ser adotado formato de backup criptografado e testada a restauracao com a chave de recuperacao.

## Condicoes antes de uso em rede

- Confirmar maquina definitiva do servidor.
- Confirmar IP ou nome de rede estavel.
- Restringir a porta do MySQL ao servidor local.
- Liberar apenas a porta da API para a rede autorizada.
- Validar backup externo criptografado e restauracao.
- Confirmar no-break ou procedimento de desligamento seguro.

