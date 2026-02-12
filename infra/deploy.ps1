# ============================================================
# AgentCore Deploy Script - Depo Stok Yonetim Sistemi
# PowerShell - Windows
# ============================================================
#
# Kullanim:
#   .\infra\deploy.ps1
#
# Onkoşul:
#   - AWS CLI kurulu ve credentials ayarli
#   - pip install bedrock-agentcore-starter-toolkit
#   - set AWS_DEFAULT_REGION=us-west-2
# ============================================================

$ErrorActionPreference = "Stop"

$REGION = if ($env:AWS_DEFAULT_REGION) { $env:AWS_DEFAULT_REGION } else { "us-west-2" }
$ROLE_NAME = "BedrockAgentCore-WarehouseStockMgmt-ExecutionRole"
$POLICY_NAME = "BedrockAgentCore-WarehouseStockMgmt-Policy"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " AgentCore Deploy - Depo Stok Yonetim" -ForegroundColor Cyan
Write-Host " Region: $REGION" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# 1. AWS kimlik kontrolu
Write-Host "`n[1/5] AWS kimlik kontrolu..." -ForegroundColor Yellow
$identity = aws sts get-caller-identity --output json | ConvertFrom-Json
$ACCOUNT_ID = $identity.Account
Write-Host "  Account: $ACCOUNT_ID"
Write-Host "  User: $($identity.Arn)"

# 2. IAM Role olustur (yoksa)
Write-Host "`n[2/5] IAM Execution Role olusturuluyor..." -ForegroundColor Yellow
$roleExists = $false
try {
    aws iam get-role --role-name $ROLE_NAME --output json 2>$null | Out-Null
    $roleExists = $true
    Write-Host "  Role zaten mevcut: $ROLE_NAME"
} catch {
    Write-Host "  Yeni role olusturuluyor: $ROLE_NAME"
}

if (-not $roleExists) {
    aws iam create-role `
        --role-name $ROLE_NAME `
        --assume-role-policy-document file://infra/agentcore_trust_policy.json `
        --description "AgentCore execution role for Warehouse Stock Management System" `
        --output json

    if ($LASTEXITCODE -ne 0) {
        Write-Host "  HATA: Role olusturulamadi!" -ForegroundColor Red
        exit 1
    }
    Write-Host "  Role olusturuldu." -ForegroundColor Green
}

# 3. Inline policy ekle / guncelle
Write-Host "`n[3/5] IAM Policy ekleniyor..." -ForegroundColor Yellow

# Policy dosyasindaki wildcard account ID'yi gercek account ID ile degistir
$policyContent = Get-Content -Path "infra/agentcore_execution_policy.json" -Raw
# Not: Policy'de zaten wildcard (*) kullaniliyor, account-specific degil

aws iam put-role-policy `
    --role-name $ROLE_NAME `
    --policy-name $POLICY_NAME `
    --policy-document file://infra/agentcore_execution_policy.json

if ($LASTEXITCODE -ne 0) {
    Write-Host "  HATA: Policy eklenemedi!" -ForegroundColor Red
    exit 1
}
Write-Host "  Policy eklendi: $POLICY_NAME" -ForegroundColor Green

$ROLE_ARN = "arn:aws:iam::${ACCOUNT_ID}:role/$ROLE_NAME"
Write-Host "  Role ARN: $ROLE_ARN"

# IAM propagation icin bekle
Write-Host "  IAM propagation icin 10 saniye bekleniyor..."
Start-Sleep -Seconds 10

# 4. AgentCore configure
Write-Host "`n[4/5] AgentCore configure..." -ForegroundColor Yellow
agentcore configure `
    -e agentcore_app.py `
    -r $REGION `
    --execution-role $ROLE_ARN `
    --non-interactive

if ($LASTEXITCODE -ne 0) {
    Write-Host "  HATA: AgentCore configure basarisiz!" -ForegroundColor Red
    exit 1
}
Write-Host "  Configure tamamlandi." -ForegroundColor Green

# 5. AgentCore deploy
Write-Host "`n[5/5] AgentCore deploy baslatiliyor..." -ForegroundColor Yellow
Write-Host "  Bu islem birkaç dakika surebilir (CodeBuild + deploy)..." -ForegroundColor Gray
agentcore deploy

if ($LASTEXITCODE -ne 0) {
    Write-Host "  HATA: Deploy basarisiz!" -ForegroundColor Red
    Write-Host "  Loglari kontrol edin: agentcore status" -ForegroundColor Gray
    exit 1
}

Write-Host "`n============================================" -ForegroundColor Green
Write-Host " DEPLOY BASARILI!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Test etmek icin:" -ForegroundColor Cyan
Write-Host '  agentcore invoke ''{"prompt": "kritik stoklari goster"}'''
Write-Host ""
Write-Host "Durum kontrolu:" -ForegroundColor Cyan
Write-Host "  agentcore status"
Write-Host ""
Write-Host "Temizlik:" -ForegroundColor Cyan
Write-Host "  agentcore destroy"
Write-Host "  aws iam delete-role-policy --role-name $ROLE_NAME --policy-name $POLICY_NAME"
Write-Host "  aws iam delete-role --role-name $ROLE_NAME"
