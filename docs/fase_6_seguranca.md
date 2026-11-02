# Fase 6 - Segurança de autenticação

As senhas novas usam Argon2id. Tokens de sessão e CSRF são gerados com fonte
criptográfica; apenas SHA-256 dos tokens é persistido. O cookie de sessão é
`HttpOnly`, `SameSite=Strict` e passa a `Secure` obrigatoriamente em produção.
Operações mutáveis autenticadas exigem cabeçalho CSRF vinculado à sessão.

Os usuários legados foram importados sem suas senhas e permanecem com
`must_reset_password=true`. Uma credencial inicial aleatória do administrador
foi gravada exclusivamente em `data/initial-admin.secret`, fora do código e dos
logs. O primeiro acesso deve trocar essa senha.

O RBAC oferece os perfis `gerente`, `atendente` e `medico` e rejeita no servidor
qualquer dependência cujo perfil não esteja autorizado. Falhas e sucessos de
login, logout, troca de senha e bloqueio por excesso são auditados sem senha,
CPF ou conteúdo clínico.
