# Revisão preliminar de segurança e LGPD

Status: **controles técnicos e aceite operacional da versão 1.0.0 aprovados**.

Esta revisão prepara a Fase 16, mas não substitui a homologação, o corte nem a
aprovação do responsável pela clínica.

## Controles comprovados

| Tema | Controle e evidência | Estado |
|---|---|---|
| Autenticação | Argon2id, senha nova mínima de 12 caracteres e troca obrigatória de senha temporária | PASS |
| Sessão | Token aleatório armazenado somente por hash, expiração, revogação e cookie `HttpOnly`/`SameSite=Strict` | PASS |
| CSRF | Cookie e cabeçalho correlacionados ao hash da sessão em toda escrita protegida | PASS |
| Autorização | Perfis aplicados pelo servidor; testes negativos por perfil | PASS |
| Concorrência | Versão otimista impede sobrescrita silenciosa | PASS |
| Laudos | Armazenamento privado, PDF validado, limite de 10 MiB e SHA-256 conferido no download | PASS |
| Financeiro | Valores decimais, soma exata, estorno preservando original e trilha de auditoria | PASS |
| Logs | JSON rotativo com ID de requisição, sem corpo, query string, cookies ou cabeçalhos | PASS |
| Backup | AES-256-GCM autenticado, chave separada, retenção de 14 arquivos e restauração ensaiada | PASS |
| Exposição | Inicializador preparado para escutar somente em `127.0.0.1` | PASS |

## Dados pessoais tratados

- identificação e contato de pacientes;
- CPF e dados de atendimento;
- agenda e vínculo com profissional;
- laudos e documentos clínicos, classificados como dados pessoais sensíveis;
- pagamentos, recibos e movimentos financeiros;
- usuários, perfis, sessões e registros de auditoria.

## Aceites operacionais concluídos

- controles de segurança/LGPD e operação HTTP exclusivamente local em `127.0.0.1` aprovados;
- política de retenção e descarte aprovada;
- Regiane confirmada como responsável por direitos do titular;
- Gabriel Gosmano e Regiane confirmados para incidentes, pelo telefone interno `1194395970`.

Homologação, senha administrativa, corte, legado somente leitura, restauração
pós-corte e aceite LGPD estão concluídos. Decisão: **GO para o manifesto final**.

## Evidência automatizada da versão 1.0.0

- Semgrep 1.183.0: 226 regras sobre 97 alvos, zero achados e zero erros.
- pip-audit 2.10.1: 46 dependências instaladas, zero vulnerabilidades conhecidas.
- SQL textual de três rotinas administrativas substituído por construção SQLAlchemy tipada.
- `cryptography` atualizado para 50.0.2 e backup AES-256-GCM restaurado em banco isolado.
- Ruff, Poetry e 29 de 29 testes aprovados.
- Corte, smoke, backup pós-corte e backup final restaurado aprovados.

Essas evidências aprovam tecnicamente a versão 1.0.0, mas não substituem o
aceite operacional de segurança/LGPD.
