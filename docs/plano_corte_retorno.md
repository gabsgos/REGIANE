# Plano de corte e retorno

Status: **executado com PASS em 01/11/2026, das 21:01:54 às 21:12:26**.

## Condições prévias obrigatórias

- termo de homologação assinado pelas três áreas;
- janela, responsáveis e canal de incidente definidos;
- senha inicial do administrador trocada;
- backup `.abelbak` e chave separados e restaurados em ensaio;
- nenhum defeito crítico/alto e health integralmente `ok`.

## Corte

1. Registrar início da janela e bloquear escrita no sistema legado.
2. Recalcular SHA-256 dos 306 arquivos e comparar ao manifesto.
3. Criar backup final da pasta legada e testar restauração temporária.
4. Criar backup criptografado do sistema novo.
5. Executar importação e normalização finais em banco limpo aprovado.
6. Comparar 296.775 registros de staging, 3.867 atendimentos e totais financeiros.
7. Aplicar `alembic upgrade head` e registrar o revision head.
8. Registrar tarefa `ABEL API`, iniciar frontend/API e manter legado somente leitura.
9. Criar/ativar usuários, sem reutilizar senhas legadas.
10. Executar smoke test somente leitura e depois transação controlada aprovada.
11. Criar backup pós-corte e monitorar health/logs durante a janela.

## Critérios de retorno

Retornar se ocorrer perda de relacionamento, divergência financeira sem
explicação, acesso indevido, laudo público, falha de persistência, health
degradado persistente ou defeito crítico/alto.

## Retorno

1. Parar a API, registrar horário e preservar logs.
2. Não apagar o banco novo; congelá-lo para análise.
3. Restaurar o backup pós-corte em ambiente isolado para preservar evidência.
4. Remover o atributo somente leitura do legado apenas com autorização do gerente.
5. Reativar o legado, validar consulta e escrita controlada e comunicar usuários.
6. Corrigir, repetir Fases 13 e 14 e aprovar uma nova janela.
