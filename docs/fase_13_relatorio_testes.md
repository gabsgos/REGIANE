# Fase 13 - Testes integrados e ensaio de migração

O release candidate foi ensaiado em `abel_rehearsal_test`, criado vazio e
removido ao final. As 14 etapas passaram em 162,147 segundos:

1. migrations completas a partir de zero e schema sem drift;
2. duas importações de 86 arquivos e 296.775 registros;
3. duas normalizações, 3.867 atendimentos e total 409.829,41;
4. reconciliação e amostra determinística;
5. pacientes/atendimentos, financeiro, documentos, administração e relatórios;
6. permissões negativas por médico e atendente;
7. concorrência otimista real e frontend integrado.

Duas atualizações simultâneas da mesma versão resultaram em HTTP 200 e HTTP
409, sem perda silenciosa. Quarenta consultas foram executadas com oito workers:
média 132,753 ms, p95 232,576 ms e máximo 234,823 ms.

O banco de produção apresentou contagens idênticas antes e depois do ensaio. O
banco descartável foi removido. Não permanecem defeitos críticos ou altos
conhecidos; as 510 ocorrências de dados legados continuam na fila de revisão e
não são defeitos de software ocultos.
