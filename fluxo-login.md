# Fluxo de login, sessão, cache e segurança

**Data da análise:** 2026-11-05 12:12:39 -03:00  
**Escopo:** comparação documental entre o ABEL/Regiane Front e o FISIA. Nenhum código, banco ou serviço foi alterado nesta análise.

## 1. Evidências analisadas

### ABEL

- `backend/app/core/config.py`
- `backend/app/api/routes/auth.py`
- `backend/app/api/dependencies.py`
- `backend/app/main.py`
- `regianefront/app.py`
- `regianefront/config.py`
- `regianefront/data_access/abel_api_adapter.py`
- `regianefront/components/sidebar.py`
- Build observada: `1.0.0+build.60`.

### FISIA

- `src/vanilla/main.ts`
- `src/lib/types.ts`
- `pwa/pwa-sw.js`
- `package.json` (`0.1.165`).

O `poetry check` passou no ABEL e no `regianefront`.

## 2. Modelo atual do ABEL

### Login

1. O navegador envia `POST /abel/api/auth/login` com usuário e senha, usando `credentials: include`.
2. O backend normaliza o usuário, verifica se está ativo e compara a senha com Argon2id.
3. Falhas são limitadas por usuário/origem: cinco tentativas em janela de 300 segundos.
4. Em sucesso, o backend cria uma sessão aleatória e grava somente o hash do token no banco (`AuthSession`).
5. A sessão recebe expiração absoluta de seis horas e guarda `access_version` para revogação em massa.
6. O servidor retorna dois cookies:
   - `abel_session`: HttpOnly, SameSite Strict e Secure em produção.
   - `abel_csrf`: legível pelo navegador e usado no cabeçalho `X-CSRF-Token`.

### Validação de cada requisição

1. O backend lê `abel_session`, calcula seu hash e procura uma sessão não revogada e ainda válida.
2. Confere usuário ativo e `access_version` atual.
3. Carrega papéis, workspace e permissões.
4. Atualiza `last_seen_at`.
5. Operações mutáveis exigem correspondência entre cookie CSRF e cabeçalho CSRF.
6. Permissões privilegiadas podem exigir step-up dentro da janela configurada de 15 minutos.

### Renovação/heartbeat

- O servidor verifica a sessão em toda requisição autenticada.
- O front-end chama `/auth/me` a cada 15 minutos com `cache: no-store`.
- A expiração real continua sendo determinada pelo servidor; o timer do navegador não é autoridade de segurança.

### Logout e revogação

- `POST /abel/api/auth/logout` revoga a sessão atual, grava auditoria e remove os dois cookies.
- Alteração de senha incrementa `access_version`, revoga sessões ativas e remove cookies.
- Alterações de privilégio devem seguir o mesmo padrão de revogação/rotação.

### Cache no ABEL

- Não foi identificado cache de respostas clínicas como fonte de verdade no backend.
- Chamadas de autenticação usam `no-store`.
- O adaptador usa cookies da requisição; não guarda token de autenticação em `localStorage` ou `sessionStorage`.
- SQLite é apenas um adaptador de dados legado/local, não um cache de sessão.

### Riscos/gaps atuais

- `regianefront/app.py` remove `Secure` e transforma `SameSite=Strict` em `SameSite=Lax` no proxy. Isso reduz a proteção e deve ser eliminado em produção.
- `regianefront/config.py` mantém `enable_auth=False` como configuração de desenvolvimento, embora o overlay ainda consulte o backend. Isso pode gerar falsa sensação de proteção local.
- Fechar a aba não é uma garantia confiável de logout; a garantia deve ser expiração/revogação no servidor.
- Não foi localizado, na inspeção realizada de `backend/app/main.py`, um conjunto explícito de headers globais de segurança; validar antes do release.

## 3. Modelo atual do FISIA

### Bootstrap e login

1. A SPA chama `GET /api/web/session` no carregamento.
2. Se a sessão estiver válida, carrega o usuário e o contexto ativo; se não, mostra a tela de login.
3. O login envia `POST /api/web/login` com login, segredo, `rememberDevice` e eventual token de vínculo.
4. Alguns fluxos podem retornar `next: "code"`; nesse caso a SPA envia o código para `/api/web/login/code`.
5. As chamadas usam `credentials: include`; o cookie é a autoridade de sessão. O checkout frontend não contém a implementação server-side dos atributos do cookie, então HttpOnly/Secure/SameSite precisam ser confirmados no backend FISIA.

### Contexto e isolamento

Cada chamada autenticada pode levar:

- `X-FISIA-Workspace-Id`
- `X-FISIA-Membership-Id`
- `X-FISIA-Unit-Id`
- `X-FISIA-Facility-Id`
- `X-FISIA-Scope-Mode`

O contexto ativo é validado no servidor. Chaves locais de contexto recente são apenas conveniência visual, não autorização.

### Logout

1. A SPA chama `POST /api/web/logout`.
2. Interrompe o watcher de cache.
3. Limpa o identificador do proprietário do cache e o usuário em memória.
4. Volta para a rota inicial e renderiza a tela de login.

### Cache seguro

- IndexedDB: `fisia-secure-cache-v1`.
- Respostas e rascunhos são criptografados com AES-GCM usando chave efêmera em memória.
- A chave gira por sessão e expira em uma hora.
- A chave de armazenamento inclui sessão, usuário, workspace, unidade, facility, escopo e rota.
- Cache fresco: uma hora; cache stale: uma hora adicional para permitir atualização controlada.
- A revisão do servidor é verificada a cada 15 minutos e quando a página retorna à visibilidade.
- Mudança de revisão, troca de usuário/contexto e respostas 401/403 limpam o cache.
- O service worker `pwa/pwa-sw.js` pode cachear assets estáticos; dados clínicos devem continuar sob o cache seguro da aplicação.

### Limites do FISIA

- `localStorage`/`sessionStorage` também armazenam preferências, onboarding, contadores e tokens de fluxos específicos; não devem ser tratados como sessão principal.
- O tipo local de conta contém campo de senha em dados locais de onboarding; isso é aceitável somente para demonstração e deve ser removido/neutralizado em produção.
- Os atributos exatos dos cookies não estão disponíveis neste checkout frontend.

## 4. Comparação

| Tema | ABEL | FISIA |
|---|---|---|
| Autoridade de sessão | Cookie `abel_session` + linha no banco | Cookie web + `/api/web/session` |
| Expiração | 6 horas absolutas | Sessão definida pelo backend; cache seguro de 1 hora |
| Verificação periódica | `/auth/me` a cada 15 min | Revisão de cache a cada 15 min; sessão consultada no bootstrap/401 |
| CSRF | Cookie legível + `X-CSRF-Token` | Contrato depende do backend; frontend usa `sendJson` |
| Cache de dados | Sem cache clínico persistente identificado | IndexedDB criptografado e escopado |
| Isolamento | workspace, manager, papéis e `access_version` | workspace/membership/unit/facility/scope |
| Logout | Revoga sessão no servidor e remove cookies | Endpoint de logout + limpeza local de estado/cache |
| Principal risco | Proxy enfraquece Secure/SameSite | Cookie server-side não verificável neste checkout |

## 5. Modelo recomendado para unificar o ABEL

1. Manter sessão server-side com cookie HttpOnly aleatório; nunca colocar token ou senha em armazenamento Web.
2. Manter `abel_session` com `Secure` em HTTPS, `SameSite=Strict` e `Path=/`. Usar Lax somente se uma integração cross-site for comprovadamente necessária.
3. Remover a reescrita de cookies que elimina `Secure` e troca Strict por Lax.
4. Manter expiração absoluta de seis horas e verificação server-side em cada requisição.
5. Manter heartbeat de 15 minutos no front-end, sempre com `no-store`.
6. Revogar e rotacionar sessão após login, logout, troca de senha, troca de workspace e mudança de papéis privilegiados.
7. Aplicar `Cache-Control: no-store` a autenticação, dados clínicos, agenda e financeiro.
8. Se for necessário cache de interface, usar somente dados cifrados, com proprietário usuário/workspace, TTL curto, revisão de servidor e limpeza em logout/401/403.
9. Manter isolamento por `workspace_id`; papéis múltiplos devem resultar na união de permissões, nunca em acesso fora do workspace.
10. Adicionar headers globais: CSP, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` e proteção anti-clickjacking compatível com o layout.

## 6. Fluxos detalhados de segurança

### A. Primeiro acesso

O navegador carrega a aplicação, consulta `/auth/me` ou `/api/web/session`, não recebe uma sessão válida e exibe login. Nenhum dado clínico deve ser carregado antes dessa decisão.

### B. Login bem-sucedido

Credenciais válidas criam sessão server-side, cookies seguros e contexto autorizado. A aplicação então carrega apenas menus, agenda, RENACH e financeiro permitidos pelos papéis e workspace.

### C. Login inválido/rate limit

O backend responde erro genérico, não revela se o usuário existe, registra auditoria e bloqueia novas tentativas após o limite. O front-end não deve persistir senha nem token.

### D. Requisição autenticada

Cookie é validado no banco, `access_version` é comparado, workspace/papéis são carregados e, para mutações, CSRF é verificado. Falha retorna 401/403 e o front limpa estado sensível.

### E. Expiração

Ao atingir seis horas, ou ao detectar revogação, a próxima chamada recebe 401. O front limpa cache/estado, encerra a sessão visual e redireciona ao login.

### F. Logout explícito

O botão chama o endpoint de logout; o servidor revoga a sessão e remove cookies. O front limpa memória, IndexedDB/cache de respostas e retorna ao login.

### G. Fechamento da aba

Não confiar em `beforeunload` para segurança. A sessão permanece válida até logout, revogação ou expiração; para exigir novo login ao fechar, seria necessário usar sessão de aba (`Max-Age` ausente) ou um mecanismo adicional, decisão que conflita com a validade de seis horas.

### H. Alteração de senha/permissão

Exige CSRF, registra auditoria, incrementa `access_version`, invalida sessões anteriores e obriga novo login em outros dispositivos.

### I. Cache seguro

Cache só é aceito quando pertence ao mesmo usuário/workspace, não expirou e a revisão do servidor não mudou. Caso contrário, busca rede; 401/403, logout ou troca de contexto limpam tudo.

## 7. Gates antes de implementar

- Confirmar no backend FISIA os atributos reais dos cookies e a política de expiração.
- Remover o downgrade de cookies no proxy do Regiane Front.
- Decidir se `enable_auth=False` permanecerá apenas em ambiente local isolado.
- Validar headers de segurança globais do ABEL.
- Testar login, logout, expiração, CSRF, troca de papel, troca de workspace e limpeza de cache em navegador real.
- Testar que nenhum perfil acessa agenda/RENACH/financeiro de outro workspace.

## Decisão desta revisão

O ABEL tem um modelo server-side mais explícito e adequado como fonte de verdade. O FISIA tem o modelo de cache local mais completo e deve inspirar a camada opcional de cache cifrado, mas não substituir a sessão server-side. A próxima alteração de código deve ser feita somente após alinhar esses contratos compartilhados com a Pessoa A.

## 8. Plano de implementação no ABEL

### Fase 0 — Baseline e contrato compartilhado

- Registrar versão, branch, build e estado do banco.
- Confirmar com a Pessoa A os arquivos compartilhados: `regianefront/app.py`, navegação e contratos `/auth/*`.
- Definir ambientes local, tablet/homologação e produção.

**Gate:** contrato documentado, Poetry aprovado e nenhum segredo no repositório.

### Fase 1 — Cookies e proxy

- Remover a transformação de `SameSite=Strict` para `Lax`.
- Não remover `Secure` em HTTPS.
- Manter `HttpOnly` na sessão.
- Testar os atributos reais de `Set-Cookie`.

**Gate:** login HTTPS com cookies `Secure`, `HttpOnly` e SameSite aprovado.

### Fase 2 — Sessão e revogação

- Manter TTL absoluto de seis horas.
- Validar sessão no servidor em toda requisição.
- Rotacionar sessão após login.
- Revogar no logout.
- Revogar sessões após troca de senha ou privilégios.
- Usar `access_version` para invalidar sessões antigas.
- Padronizar respostas 401 e redirecionamento ao login.

**Gate:** testes de login, logout, expiração, revogação e novo login aprovados.

### Fase 3 — Heartbeat e recuperação do frontend

- Manter `/auth/me` a cada 15 minutos com `cache: no-store`.
- Ao receber 401, limpar estado sensível e redirecionar ao login.
- Ao receber 403, manter a sessão e bloquear somente a ação não autorizada.
- Atualizar o nome do usuário a partir de `/auth/me`.
- Não tratar fechamento da aba como garantia de segurança.

**Gate:** simulações de 401/403 e perda de conexão sem loop de carregamento.

### Fase 4 — CSRF

- Exigir `X-CSRF-Token` em toda operação mutável.
- Validar cookie, cabeçalho e digest persistido.
- Testar token ausente, inválido e válido.

**Gate:** nenhuma escrita aceita requisição sem CSRF válido.

### Fase 5 — Cache seguro opcional

- Começar sem cache persistente para autenticação, agenda, RENACH e financeiro.
- Se necessário, usar IndexedDB cifrado, chave efêmera em memória e TTL curto.
- Escopar por usuário/workspace.
- Limpar em logout, 401, 403, troca de workspace, papéis ou revisão.
- Nunca gravar senha, token ou cookie em `localStorage`.

**Gate:** usuários e workspaces diferentes não reutilizam dados.

### Fase 6 — Workspace e múltiplos papéis

- Calcular permissões pela união dos papéis.
- Manter `workspace_id` como isolamento obrigatório.
- Revalidar papéis no backend.
- Rotacionar ou revogar sessão após mudança de privilégio.
- Testar combinações como gestora + psicóloga.

**Gate:** nenhum perfil acessa dados de outro workspace.

### Fase 7 — Headers HTTP

- Adicionar CSP, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` e proteção contra clickjacking.
- Aplicar `Cache-Control: no-store` a autenticação e dados clínicos.

**Gate:** inspeção de headers em local, tablet e HTTPS.

### Fase 8 — Auditoria

- Auditar login aprovado/falho, rate limit, logout, senha alterada, papel alterado e revogação.
- Associar usuário, workspace, request ID, origem e horário.
- Nunca registrar senha, token, cookie ou dados clínicos completos.

**Gate:** eventos críticos registrados e sanitizados.

### Fase 9 — Testes de segurança

- Login correto/incorreto e limite de tentativas.
- Logout e expiração.
- Troca de senha e revogação.
- CSRF ausente, inválido e válido.
- Usuários ativos/inativos.
- Gestor, recepção, médico, psicólogo e múltiplos papéis.
- Troca de workspace e tentativa de acesso cruzado.
- Cache após logout, 401, 403 e troca de usuário.
- Navegador anônimo, celular e tablet.

**Gate:** testes automatizados e smoke test autenticado sem regressões.

### Fase 10 — Homologação e release

- Gerar build identificável.
- Fazer backup antes de atualizar o tablet.
- Aplicar migration somente se reversível.
- Reiniciar serviços.
- Executar health check, login, logout e smoke test.
- Registrar commit, arquivos, impactos e rollback.

**Gate final:** aprovação humana de segurança, autenticação, permissões e cache antes de deploy/push.

### Ordem de execução

`0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10`

Não há autorização de deploy nesta revisão; tablet e repositórios permanecem sem alteração.

## Status da implementação local — 2026-11-05

- Fases 0 a 4: concluídas localmente; CSRF existente foi preservado e os endpoints de autenticação passaram a enviar `Cache-Control: no-store` e `Pragma: no-cache`.
- Fase 5: baseline seguro adotado sem cache persistente de credenciais; respostas sensíveis permanecem não armazenáveis.
- Fases 6 e 8: modelo server-side de sessão, workspace, papéis múltiplos e auditoria existentes foram mantidos.
- Fase 7: headers HTTP globais adicionados no backend e `no-store` aplicado às famílias de endpoints clínicos, financeiros, documentos, relatórios e autenticação.
- Fase 9: gate automatizado aprovado (`14 passed` nos testes de segurança, frontend e health); compilação, Poetry e diff aprovados.
- Fase 10: não executada; não houve deploy, restart de serviços, commit ou push nesta solicitação.
