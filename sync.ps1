# Script para automatizar o envio de alterações para o GitHub
$current_branch = git rev-parse --abbrev-ref HEAD
if ($current_branch -eq "main") {
    Write-Host "[ERRO] Voce esta na branch 'main'. Por seguranca, este script nao pode ser executado aqui." -ForegroundColor Red
    exit
}
$commit_message = Read-Host "Digite a sua mensagem de commit"
if ([string]::IsNullOrWhiteSpace($commit_message)) {
    Write-Host "[ERRO] A mensagem de commit nao pode estar vazia." -ForegroundColor Red
    exit
}
Write-Host ""
Write-Host "[INFO] Iniciando sincronizacao para a branch: $current_branch" -ForegroundColor Green
git add .
git commit -m "$commit_message"
git push origin $current_branch
if ($LASTEXITCODE -eq 0) {
    Write-Host "[SUCESSO] Sincronizacao concluida com sucesso!" -ForegroundColor Green
    Write-Host ">> Proximo passo: Crie o Pull Request no GitHub no link abaixo:"
    Write-Host "https://github.com/dieterbg/cuideme-mvp/pull/new/$current_branch"
} else {
    Write-Host "[ERRO] Falha no envio para o GitHub. Verifique as mensagens de erro acima." -ForegroundColor Red
}