# Fase 2 - Dicionario e qualidade do legado

## Escopo

Foram analisados os arquivos da copia original `ABEL-BAK` sem alteracao da fonte e sem
exportacao de valores pessoais. O inventario e reproduzido por `tools/legacy_inventory.py`
com oito workers.

## Resumo

- 54 DBFs ativos.
- 86 arquivos realmente em formato DBF.
- 32 snapshots ou modelos DBF com extensoes alternativas.
- 292699 registros ativos.
- 121 registros exatamente duplicados.
- 0 datas com formato invalido.
- 3389 datas formalmente validas, mas fora do intervalo operacional esperado.
- 0 valores numericos com formato invalido.
- 10 relacionamentos inferidos e testados.
- 11 linhas orfas, todas em `CANDIDAT.ORIGEM` e concentradas em uma chave ausente.

## Achados

### Alta severidade

1. `USUARIOS.SENHA` e senhas administrativas em `GERADOR` pertencem a um modelo de
   credenciais legado. Elas nao devem ser promovidas ao sistema novo.
2. `CANDIDAT.DT_VALID` possui 3381 datas anteriores a 1900. O valor original deve permanecer
   em staging, mas a data normalizada deve ficar nula ate revisao ou regra de negocio.
3. O cadastro central mistura pessoa, atendimento, resultado, profissional e financeiro. A
   migracao direta para uma unica tabela perpetuaria o problema de granularidade.

### Media severidade

1. Oito datas de nascimento sao anteriores a 1900.
2. Existem 121 duplicados exatos: 114 em `TABMP`, 5 em `FANLAN` e 2 em `CIRETRAN`.
3. Existem 11 referencias orfas de origem em `CANDIDAT`.
4. CPF esta vazio em 13 registros e aparece repetido em 59 chaves, envolvendo 118 linhas. A
   repeticao pode representar atendimentos distintos e nao deve ser deduplicada cegamente.
5. RENACH e PGU estao quase totalmente vazios no conjunto atual.

### Baixa severidade

1. Datas de cabecalho de varios DBFs antigos usam ano nao padrao; a data do sistema de
   arquivos deve ser preservada como evidencia auxiliar.
2. Arquivos TXT e 188 revelam evolucao de esquema e devem ser mantidos como snapshots, sem
   prevalecer sobre os DBFs ativos.

## Integridade confirmada

- `CANDIDAT.CODIGO` tem 3867 valores preenchidos e unicos.
- Pagamentos, depositos, cartoes e programacoes de cartao possuem 100% de cobertura para
  `CANDIDAT.CODIGO` nos relacionamentos testados.
- Eventos de pagamento possuem 100% de cobertura em `EVENTOS.CODIGO`.
- Lancamentos e saldos possuem 100% de cobertura em `CONTBAN.CONTA`.

## Decisao

O legado e utilizavel como fonte de migracao quando importado primeiro para staging
imutavel. A promocao para tabelas normalizadas deve aplicar as regras documentadas e manter
fila de revisao para datas implausiveis, CPFs ausentes e referencias orfas.
