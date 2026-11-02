# Fase 11 - Administração e relatórios

Gerentes podem criar, editar, desativar e redefinir usuários. Senhas temporárias
são exibidas uma única vez, armazenadas apenas como Argon2 e exigem redefinição.
Atendentes e médicos recebem HTTP 403 nos endpoints administrativos.

Relatórios aceitam período, profissional, evento e forma de pagamento. A
resposta repete os filtros aplicados e calcula atendimentos, pacientes e total
pago. O fechamento diário compara pagamentos e recibos. O painel de migração
agrupa as 510 ocorrências rastreáveis sem expor os payloads clínicos.

A exportação CSV exige gerente, registra período e número de linhas na auditoria
e neutraliza células iniciadas por `=`, `+`, `-` ou `@`. O ensaio comparou API e
consultas SQL independentes, com contagens e valores idênticos.
