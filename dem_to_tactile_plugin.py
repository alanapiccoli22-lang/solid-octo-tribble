# Clone o repositório (se ainda não tiver localmente)
git clone https://github.com/alanapiccoli22-lang/solid-octo-tribble.git
cd solid-octo-tribble

# Remove todos os arquivos existentes (exceto a pasta .git)
git rm -rf *

# Copie sua pasta nova para dentro deste diretório
# (arraste os arquivos novos para cá, ou use cp/mv)

# Adicione, comite e envie
git add .
git commit -m "Substitui arquivos antigos pela nova estrutura"
git push
