#!/bin/bash

# --- Script para automatizar o envio de alterações para o GitHub ---

# Pega o nome da branch atual
current_branch=$(git rev-parse --abbrev-ref HEAD)

# 1. Trava de segurança: impede a execução na branch 'main'
if [ "$current_branch" == "main" ]; then
  echo "❌ ERRO: Você está na branch 'main'. Por segurança, este script não pode ser executado aqui."
  echo "Crie uma nova branch para suas alterações com: git checkout -b nome-da-sua-branch"
  exit 1
fi

# 2. Pede a mensagem de commit
read -p "📝 Digite a sua mensagem de commit: " commit_message

# Verifica se a mensagem de commit foi inserida
if [ -z "$commit_message" ]; then
    echo "❌ ERRO: A mensagem de commit não pode estar vazia."
    exit 1
fi

echo ""
echo "-------------------------------------------"
echo "🚀 Iniciando sincronização para a branch: $current_branch"
echo "-------------------------------------------"

# 3. Executa os comandos Git
echo "➡️ Adicionando todos os arquivos (git add .)"
git add .

echo "➡️ Fazendo o commit com a mensagem: '$commit_message'"
git commit -m "$commit_message"

echo "➡️ Enviando para o GitHub (git push origin $current_branch)"
git push origin $current_branch

# Verifica se o push foi bem-sucedido
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Sincronização concluída com sucesso!"
    echo "👉 Próximo passo: Crie o Pull Request no GitHub no link abaixo:"
    echo "https://github.com/dieterbg/cuideme-mvp/pull/new/$current_branch"
else
    echo "❌ Falha no envio para o GitHub. Verifique as mensagens de erro acima."
fi