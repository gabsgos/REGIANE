# Frontend

O frontend modular da Fase 10 e servido pelo FastAPI em `/`. A pagina inicial da raiz e
mantida sincronizada com `frontend/index.html`.

Autenticacao, pacientes, atendimentos, financeiro e documentos usam a API. Dados clinicos
e credenciais nao sao gravados em armazenamento persistente do navegador.

O modulo financeiro oferece:

- resumo operacional diario para gerente e atendente;
- relatorio global de gerente por periodo e usuario, com serie temporal e extrato paginado;
- relatorio individual por paciente, com resumo, evolucao mensal, pagamentos, atendimentos e recibos;
- exportacoes CSV auditadas no backend;
- busca administrativa de usuarios por nome ou identificador de acesso.

