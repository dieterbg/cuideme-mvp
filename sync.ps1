# --- Script para automatizar o envio de alterações para o GitHub ---

# Pega o nome da branch atual
$current_branch = git rev-parse --abbrev-ref HEAD

# 1. Trava de segurança: impede a execução na branch 'main'
if ($current_branch -eq "main") {
    Write-Host "[ERRO] Voce esta na branch 'main'. Por seguranca, este script nao pode ser executado aqui." -ForegroundColor Red
    Write-Host "Crie uma nova branch para suas alteracoes com: git checkout -b nome-da-sua-branch"
    exit
}

# 2. Pede a mensagem de commit
$commit_message = Read-Host "Digite a sua mensagem de commit"

# Verifica se a mensagem de commit foi inserida
if ([string]::IsNullOrWhiteSpace($commit_message)) {
    Write-Host "[ERRO] A mensagem de commit nao pode estar vazia." -ForegroundColor Red
    exit
}

Write-Host ""
Write-Host "-------------------------------------------"
Write-Host "[INFO] Iniciando sincronizacao para a branch: $current_branch" -ForegroundColor Green
Write-Host "-------------------------------------------"

# 3. Executa os comandos Git
Write-Host ">> Adicionando todos os arquivos (git add .)"
git add .

Write-Host ">> Fazendo o commit com a mensagem: '$commit_message'"
git commit -m "$commit_message"

Write-Host ">> Enviando para o GitHub (git push origin $current_branch)"
git push origin $current_branch

# Verifica se o último comando foi bem-sucedido
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[SUCESSO] Sincronizacao concluida com sucesso!" -ForegroundColor Green
    Write-Host ">> Proximo passo: Crie o Pull Request no GitHub no link abaixo:"
    Write-Host "https://github.com/dieterbg/cuideme-mvp/pull/new/$current_branch"
} else {
    Write-Host "[ERRO] Falha no envio para o GitHub. Verifique as mensagens de erro acima." -ForegroundColor Red
}