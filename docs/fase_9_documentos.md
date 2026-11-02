# Fase 9 - Laudos e documentos

Os PDFs são armazenados em `data/documents`, diretório privado que não é
montado pelo servidor web. O nome físico é aleatório; o nome enviado pelo
usuário permanece apenas como metadado. Downloads passam obrigatoriamente por
autenticação e autorização do atendimento.

O upload limita o tamanho antes do parser, exige assinatura PDF e valida a
estrutura com `pypdf`. Cada versão recebe SHA-256, tamanho, autor e número
sequencial; a versão anterior permanece registrada e inativa. O download
recalcula o hash e bloqueia qualquer arquivo alterado.

O ensaio integrou duas versões, reinicialização da aplicação, download por
médico vinculado, negação ao atendente, URL pública inexistente, limite de
tamanho e detecção de adulteração. Os dois arquivos de ensaio e seus registros
foram removidos ao final.
