# Registro de coordenação

## Entradas

### 2026-11-17 — Conferência de versões e regressões de agenda

- Responsável: Pessoa B, implementação autorizada pelo usuário nas duas áreas.
- Branches: main em ambos os repositórios. Commits base: ABEL `4b6565f`; frontend `6943d4d`. Sem PR ou novos commits nesta tarefa.
- Git: status, diffs e fetch conferidos; ambos os HEADs coincidem com origin/main. Alterações prévias em LOG.log, docs/fase_12_backup.json, app.py e config.py preservadas.
- Comparação remota: API saudável, build 61. SHA-256 e diff normalizado via SSH somente leitura. Home idêntica; local contém tabela e paginação completa ausentes no tablet. Tablet omite três campos de AppointmentOut presentes localmente. Não sobrescrever versões integralmente.
- Arquivos compartilhados: regianefront/app.py (proxy e normalização de prefixo); pages/agendamento.py e pages/cadastro.py (callbacks de modais); services/domain.py (filtro profissional). Sem alteração do contrato HTTP ou do banco.
- Correções: requests declarado no Poetry; cookies Set-Cookie repassados separadamente; proxy sem redirecionamento automático e sem cache; contexto de paciente opcional na agenda; retorno ao cadastro tratado pela própria página; filtro todos preserva resultados; comparação de IDs aceita strings; histórico decrescente de sete dias; mock apenas por opção explícita; variável inexistente corrigida; mensagem real no erro de agendamento.
- Build do frontend: 63. Poetry lock atualizado. Graphify atualizado.
- Verificações: frontend unittest 49 aprovados; backend pytest 62 aprovados com banco SQLite efêmero isolado. Execução inicial com configuração local encontrou banco indisponível e health 503. API remota retornou 200. Isto não comprova migração ou operação no MariaDB.
- Pendências: homologação autenticada no navegador; causa do 500 remoto; revisão completa de sessão/RENACH/usuários/financeiro; capacidade, encaixes e turmas ainda não implementados. Nenhum deploy, push ou merge.

### 2026-11-17 — Ciclo de sessão e saída, build 64

- Base/branch: mesmas bases anteriores, alterações locais preservadas; sem novos commits ou PR.
- Frontend: app.py e config.py; teste JavaScript em tests/test_session_browser_logic.py. Backend: tests/test_auth_http_lifecycle.py, sem alteração das rotas ou schema.
- Saída permanece na origem/prefixo atual e só redireciona após HTTP de sucesso ou sessão já inválida (401). Falha de rede/500 é informada, sem alegar logout. Tab_id removido na saída.
- Login reaparece após expiração mesmo quando a camada inicial já foi removida. Falha de verificação 500 não é tratada como credencial inválida. Aba sem tab_id exige login.
- Retirado beacon em pagehide: o evento também ocorre em reload. Fechamento usa expiração do backend em 15 minutos sem chamadas; revogação imediata no fechamento não é garantida. Cookie restaurado pelo navegador não dispensa o tab_id da aba. Esta regra ainda não fornece cookies independentes para múltiplas abas.
- Testes: 54 frontend aprovados, incluindo execução do JavaScript real de saída em Node com HTTP 204/401/500 e falha de rede. Cinco integrações HTTP autenticadas com banco efêmero validam login, cookies, logout, replay, inatividade, expiração absoluta, desativação e access_version.
- Computer Use interrompeu a verificação no Chrome porque não pôde identificar a URL atual com confiança para aplicar sua política. Sem teste visual autenticado confirmado.
- Sem deploy ou mudança do banco do tablet; próximo gate operacional permanece pendente. Não interpretar testes isolados como homologação do runtime remoto.

### 2026-11-17 13:44 -03:00 — Capacidade, turmas e fila diária

- Responsável: Pessoa B, com edição das duas áreas autorizada. Repositórios em main, bases ABEL `4b6565f` e regianefront `6943d4d`. Diffs preexistentes preservados. Sem PR ou novo commit.
- Integração: o usuário confirmou que os registros clínicos legados pertencem à HRP. O backfill de workspace foi exercitado em banco de teste. A autorização de consultas e escritas usa o workspace da sessão.
- Back-end: `backend/app/db/workspace_scope.py`, rotas `schedule.py`, `operations.py`, `clinical.py`, `documents.py` e `finance.py`. Migrações de papéis múltiplos, escopo HRP, capacidade, financeiro e escrita na fila. Logs de auditoria nas alterações da agenda.
- Front-end: `pages/agendamento.py`, `pages/renach.py`, `pages/usuarios.py`, `pages/home.py`, `pages/cadastro.py`, `services/domain.py` e adaptador ABEL. Agenda e indicadores usam os mesmos filtros. A tabela mostra origem, vínculo com histórico e ações conforme perfil. A fila mantém chegada e início no estado operacional e permite finalização clínica independente de pagamento.
- Contrato compartilhado: `/operations/schedule` para capacidade e turmas, `/appointments/{id}/arrival` e `/appointments/{id}/start` sob esse prefixo para a fila. Estados `WAITING` e `IN_PROGRESS` são aditivos. A permissão `clinical_queue.write` precisa da migration `a4e75c1d902b` em ENFORCE.
- Decisões: o dia operacional segue America/Sao_Paulo. O perfil de recepção registra chegada, o profissional atribuído inicia e conclui o exame, e a gestão pode operar o workspace. Falta preserva a reserva de capacidade do dia. Cancelamento elegível libera a vaga e mantém o histórico.
- Verificações: 83 testes pytest, inclusive reserva simultânea da última vaga no MySQL e HTTP autenticado da fila com fiscalização de perfil, CSRF e workspace. Migrações exercitadas em MySQL isolado. Frontend com 59 testes unittest e HTTP 200 para layout e dependências do Dash. Poetry, diff e Graphify verificados.
- Resultado: front e back na build 65 local. Homologação autenticada no navegador do tablet, conciliação de recebimentos e importação integral de PDF continuam no gate F5.

### 2026-11-24 — Consolidação Git integral da build 65

- Responsável: Pessoa B, back-end e servidor, com integração das duas áreas autorizada pelo usuário.
- Base: ABEL `4b6565f`; frontend `6943d4d`. Branch backend `codex/abel-build65-total-20261124`; branch frontend `codex/abel-front-build65-20261117` já integrada na `main` local pelo merge `694dde1`.
- Escopo backend: rotas e modelos de workspace, papéis múltiplos, capacidade diária, turmas, fila clínica, migrations `c91f7d2a6401`, `d02b8a316f75`, `e13c9b427a86`, `f24dab538c97` e `a4e75c1d902b`, testes e documentação operacional.
- Contratos compartilhados: agenda e fila sob `/operations/schedule`, ações de chegada e início, estados `WAITING` e `IN_PROGRESS`, permissão `clinical_queue.write` e campos de escopo por workspace.
- Arquivos preservados fora do Git: bancos MySQL descartáveis em `tmp`, caches e arquivos internos do Graphify, configuração local da Serena, credenciais e o repositório frontend aninhado.
- Verificações: Poetry aprovado em ambos; backend com 82 testes aprovados em SQLite efêmero e 1 teste MySQL opt-in ignorado por ausência do banco QA descartável; frontend com 59 testes aprovados; diff check executado.
- Integração: commit backend e merge local na `main` autorizados. Frontend já limpo e integrado localmente. Nenhum push autorizado nesta etapa.
