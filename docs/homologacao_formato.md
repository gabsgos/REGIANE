# Registro verificável da homologação

1. Copiar `config/homologation_approval.example.json` para
   `data/homologation_approval.json`.
2. Cada responsável real deve validar seus fluxos e preencher nome, data com
   fuso horário e `approved: true`.
3. Preencher janela, responsáveis pelo corte/retorno e o identificador do
   controle de mudança.
4. Definir `plan_approved` e `operator_confirmation` como `true` somente após
   aprovação real.
5. Executar:

   `poetry run python -m tools.validate_homologation`

O arquivo real permanece em `data/`, fora do código-fonte. O validador confere
os três perfis, datas, janela, confirmação do operador e hashes do piloto e do
plano de corte. Qualquer ausência ou divergência produz `NO_GO`.
