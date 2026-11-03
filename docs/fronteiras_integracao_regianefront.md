# Fronteiras de integração ABEL / regianefront

- O colaborador visual pode continuar alterando `app.py`, `assets/`, `components/`, `layouts/` e estilos.
- A integração de dados fica em `services/` e `data_access/`; alterações nas páginas devem apenas substituir chamadas por serviços.
- `DATA_BACKEND=sqlite` preserva o modo local. `DATA_BACKEND=abel_api` usa somente HTTP autenticado.
- O frontend não recebe credenciais do MariaDB e não executa SQL contra o ABEL.
- Arquivos já modificados (`app.py` e `utils/db_manager.py`) não serão sobrescritos sem conciliação explícita.

## Rollback

Definir `DATA_BACKEND=sqlite`, reiniciar o frontend e executar a suíte de testes. A API e o schema aditivo permanecem intactos; nenhum dado legado é removido.
