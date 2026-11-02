# Fase 7 - API clínica

Foram implementadas buscas paginadas, cadastro, consulta e edição de pacientes
e atendimentos. CPFs novos são validados; a ausência continua permitida para os
casos legados documentados.

Pacientes e atendimentos possuem `row_version`. Atualizações exigem a versão
lida e retornam HTTP 409 se outro usuário já tiver alterado o registro. A trilha
de auditoria guarda o estado anterior e posterior.

O escopo do médico é aplicado antes dos filtros de texto, data e status: um
filtro adicional nunca amplia a consulta. O ensaio integrado criou dois
atendimentos, vinculou somente um ao médico e confirmou que a busca do médico
retornou exatamente o registro autorizado. A gravação permaneceu após criar
uma nova instância da aplicação e foi removida ao final do ensaio.
