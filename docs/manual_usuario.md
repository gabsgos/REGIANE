# Manual do usuário ABEL

## Primeiro acesso

Abra `http://127.0.0.1:8000`, informe usuário e senha temporária e defina uma
senha nova com ao menos 12 caracteres. Credencial incorreta não libera acesso.

## Atendimento

1. Em **Atendimentos**, cadastre ou localize o paciente.
2. Crie o atendimento informando paciente, data e RENACH quando disponível.
3. Use busca, período e status; selecione o atendimento antes de pagar ou anexar laudo.
4. Se outra pessoa editar primeiro, recarregue após a mensagem de conflito.

## Recebimento

No módulo **Financeiro**, selecione o atendimento e informe os valores por PIX,
dinheiro, cartão ou cheque. A soma é o total; valores negativos e divergências
são recusados. Estorno exige gerente e motivo, sem apagar o lançamento.

## Médico ou psicólogo

O profissional visualiza somente atendimentos vinculados a ele. Em **Laudos**,
selecione PDF válido e envie. Uma nova versão preserva a anterior. Financeiro e
gestão de usuários não estão disponíveis ao perfil médico.

## Gerente

- **Usuários**: criar conta e entregar a senha temporária por canal seguro.
- **Relatórios**: informar período/filtros antes de calcular ou exportar.
- **Inconsistências**: acompanhar a fila da migração sem alterar a staging.
- **Financeiro**: revisar fechamento e justificar estornos.

## Segurança e suporte

Não compartilhe senhas, não envie laudos por URL e não copie dados de pacientes
para planilhas não autorizadas. Em falha, anote horário, ação e request ID, sem
copiar senha, CPF ou conteúdo clínico.
