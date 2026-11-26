# Contrato back-end — reunião 24/11

Versão: ABEL `1.0.0+build.66`

Branch: `codex/reuniao-24-11-backend`

OpenAPI em execução: `GET /openapi.json` (rotas publicadas também sob `/abel/api`).

## Endpoints entregues

| Função | Método e rota | Permissão |
|---|---|---|
| Intake transacional | `POST /operations/intakes` | `schedule.write` + CSRF |
| Jornada do paciente | `GET /operations/patients/{patient_id}/journey` | `demographic.read` |
| Checkout congelado | `GET /operations/appointments/{appointment_id}/checkout` | `finance.receive` |
| Checkout compatível legado | `GET /finance/appointments/{appointment_id}/checkout` | `finance.receive` |
| Disponibilidade | `GET /operations/schedule/professionals/{professional_id}/availability` | `schedule.read` |
| Retornos elegíveis | `GET /operations/patients/{patient_id}/appointments/return-eligible` | `schedule.read` |

As rotas mutáveis continuam usando o cookie de sessão, CSRF e o escopo do
workspace já existentes. Profissionais só recebem atendimentos pertencentes ao
próprio escopo clínico.

## Regras congeladas

- O intake reutiliza paciente por CPF e cria cadastro quando o CPF não existe ou
  não foi informado.
- Exame médico e psicotécnico são atendimentos independentes.
- `source_key` do atendimento é derivado no servidor de workspace,
  `idempotency_key` e serviço; o navegador não escolhe a chave persistida.
- Repetir a mesma chave e payload não duplica registros; reutilizar a chave com
  outro payload retorna `409`.
- Pagamento exige atendimento e preço ativo do serviço, aceita Pix, dinheiro ou
  composição híbrida e rejeita soma/preço divergentes.
- Conclusão clínica exige RENACH ativo com estado `PDF_AUTENTICADO`.
- A configuração de disponibilidade reutiliza a permissão existente
  `schedule.manage_availability`; não foi criada uma permissão duplicada.
- Retorno exige episódio anterior compatível e ainda elegível.

## Fixtures sanitizadas

- `tests/fixtures/reuniao_24_11_contract.json`: paciente existente e dois exames.
- `tests/fixtures/reuniao_24_11_intake_new_patient.json`: paciente novo.
- `tests/fixtures/reuniao_24_11_return.json`: retorno vinculado.
- `tests/fixtures/reuniao_24_11_hybrid_payment.json`: pagamento híbrido.

Os testes de contrato validam essas fixtures diretamente contra os DTOs Pydantic
e confirmam as rotas no schema OpenAPI.

## Banco

- `b5c8e4a7d901`: controle atômico/idempotente de intake.
- `c6d9f2b8e104`: horário inicial/final nas exceções de agenda por data.

Aplicar as migrations somente após backup e homologação no mesmo dialeto do
ambiente de destino.
