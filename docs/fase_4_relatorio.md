# Fase 4 - Importação DBF para staging

Foram detectados e importados os 86 arquivos em formato DBF, incluindo os 54
arquivos `.DBF` ativos e os 32 snapshots com extensões alternativas. A carga
preserva arquivo, tabela, posição física, flag de exclusão, hash SHA-256 do
registro e o payload original decodificado em CP1252.

- Registros físicos esperados: 296.775
- Registros em `legacy_raw_records`: 296.775
- Arquivos com erro: 0
- Hashes iguais ao manifesto da Fase 0: 86/86
- Primeira carga: 34,566 s
- Segunda carga: 69,061 s
- Registros após repetição: 296.775, sem duplicação

O único campo memo encontrado (`CANDIDAT.HISTORICO`) está vazio em todos os
registros. O leitor FPT permanece implementado para ponteiros válidos. Nenhum
arquivo de origem foi escrito ou teve hash alterado.
