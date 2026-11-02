# Fase 10 - Frontend integrado

A página inicial foi modularizada em HTML, CSS e JavaScript e é servida pelo
FastAPI. O login simulado, credenciais de exemplo e dados mockados foram
removidos. Sessão, pacientes, atendimentos, pagamentos, indicadores e laudos
usam exclusivamente a API.

O cliente central envia cookies same-origin e CSRF sem persistir credenciais no
navegador. Conteúdo retornado é construído com `textContent` e `createElement`;
não há `innerHTML`. Módulos e ações são ocultados conforme os perfis retornados
pelo servidor, sem substituir a autorização da API.

O layout foi inspecionado em navegador real nas dimensões desktop (1366x768) e
tablet (768x1024). A QA encontrou a sobreposição da tela de redefinição pelo CSS;
a regra global de `hidden` foi corrigida e a inspeção repetida sem rolagem ou
conteúdo oculto visível.
