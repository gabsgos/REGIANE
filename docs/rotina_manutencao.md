# Rotina de manutenção ABEL

## Diária

- confirmar `/api/health` integralmente `ok`;
- verificar erros no log sem copiar dados sensíveis;
- conferir sucesso, tamanho e data do backup criptografado;
- confirmar espaço livre e estado do MySQL/API.

## Semanal

- revisar falhas de login, acessos negados e eventos administrativos;
- conferir usuários ativos, perfis e vínculos profissionais;
- validar hashes de uma amostra de laudos;
- verificar se a tarefa de backup continua habilitada.

## Mensal

- restaurar o backup mais recente em banco isolado e guardar o relatório;
- revisar contas sem uso e revogar acessos desnecessários;
- revisar capacidade do banco, documentos, logs e backups;
- aplicar correções somente após backup, teste e incremento de versão/build.

## Trimestral

- revisar dependências e vulnerabilidades em ambiente de teste;
- repetir testes de permissões, concorrência, backup e recuperação;
- revisar política de retenção e descarte com o responsável da clínica;
- atualizar manuais, responsáveis e contatos de incidente.

## Incidente

1. preservar logs e horários sem divulgar dados pessoais;
2. interromper somente o componente afetado;
3. informar gerente e responsáveis definidos no plano de retorno;
4. restaurar primeiro em ambiente isolado;
5. registrar causa, impacto, correção, validação e build no `LOG.log`.

Operações Git permanecem fora desta rotina até autorização explícita.
