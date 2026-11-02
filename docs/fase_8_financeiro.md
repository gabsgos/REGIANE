# Fase 8 - Financeiro

Pagamentos aceitam itens PIX, dinheiro, cartão e cheque. A API rejeita valores
negativos e exige igualdade decimal exata entre itens e total. O resumo por
período calcula quantidade, total, formas de pagamento e estornos diretamente
no banco.

Estorno exige gerente, motivo e versão atual. O pagamento e seus itens não são
apagados: o status passa a `estornado`, com autor, data, motivo e auditoria.
Recibos recebem número não previsível e permanecem vinculados a paciente e
atendimento.

No ensaio integrado, PIX 60,00 mais dinheiro 40,00 resultou em 100,00; os dois
indicadores independentes aumentaram exatamente nesses valores. Após estorno,
o total pago voltou à linha de base e o lançamento original permaneceu
consultável. O perfil médico recebeu HTTP 403 ao tentar consultar o financeiro.
