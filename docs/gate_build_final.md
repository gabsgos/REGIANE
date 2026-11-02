# Gate automatizado da build final

O comando `poetry run python -m tools.final_release_gate` valida a conclusão
das Fases 14 a 16 sem assumir sucesso pela ausência de erros. O resultado é
gravado em `docs/final_release_gate.json`.

O gate exige simultaneamente:

- homologação humana validada e Fase 14 aprovada;
- relatório de corte com produção ativa, legado somente leitura e nenhuma perda;
- smoke test posterior ao corte;
- backup posterior ao corte restaurado em ambiente isolado;
- preflight de segurança aprovado e correspondente à versão atual do projeto;
- validação final sem defeitos críticos ou altos;
- manifesto final íntegro;
- versão do projeto exatamente `1.0.0`;
- ausência de `build.txt`.

Qualquer arquivo ausente, inválido ou critério falso produz `NO_GO` e código de
saída 2. O validador não executa corte, migração, backup ou mudança de versão.
