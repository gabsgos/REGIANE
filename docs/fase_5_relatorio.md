# Fase 5 - Normalização e reconciliação

A normalização foi executada duas vezes e produziu as mesmas contagens, sem
duplicação. A staging permanece intacta e cada entidade criada possui vínculo
em `legacy_import_map`.

- Pacientes: 3.808, após consolidação controlada por CPF válido.
- Atendimentos: 3.867, todos com `legacy_code` único.
- Profissionais: 8; usuários legados: 4, sem reutilizar senhas.
- Pagamentos: 3.923; total legado e novo: 409.829,41.
- Recibos vinculados: 3.723; 11 sem correspondência permanecem em revisão.
- Movimentos financeiros: 3.827.
- Cobertura auxiliar: 2.774 depósitos, 171 cartões e 167 programações.
- Mapa legado-novo: 22.339 vínculos.

As 510 ocorrências abertas são rastreáveis: 486 datas de exame substituídas
pela data de atualização, 13 CPFs ausentes ou inválidos e 11 recibos sem
correspondência segura. Nenhum registro foi apagado da staging. A amostra
determinística de 25 atendimentos conferiu nome e data em 25/25 casos.
