# .env dosyasini okuyup environment'a yukle, sonra deploy et
$envFile = Join-Path $PSScriptRoot "..\\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
    Write-Host ".env yuklendi." -ForegroundColor Green
} else {
    Write-Host ".env dosyasi bulunamadi!" -ForegroundColor Red
    exit 1
}

# SSL workaround
$env:AWS_CA_BUNDLE = ""
$env:CURL_CA_BUNDLE = ""

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " AgentCore Deploy" -ForegroundColor Cyan
Write-Host " Region: $env:AWS_DEFAULT_REGION" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# Kimlik kontrol (boto3 ile)
Write-Host "`n[1/3] AWS kimlik kontrolu..." -ForegroundColor Yellow
python infra/check_creds.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Credential hatasi!" -ForegroundColor Red
    exit 1
}

$ROLE_ARN = "arn:aws:iam::711852701344:role/BedrockAgentCore-WarehouseStockMgmt-ExecutionRole"

# Configure
Write-Host "`n[2/3] AgentCore configure..." -ForegroundColor Yellow
agentcore configure -e agentcore_app.py -r $env:AWS_DEFAULT_REGION --execution-role $ROLE_ARN --non-interactive
if ($LASTEXITCODE -ne 0) {
    Write-Host "Configure basarisiz!" -ForegroundColor Red
    exit 1
}
Write-Host "Configure OK." -ForegroundColor Green

# Deploy
Write-Host "`n[3/3] AgentCore deploy..." -ForegroundColor Yellow
Write-Host "Bu birkac dakika surebilir..." -ForegroundColor Gray
agentcore deploy
if ($LASTEXITCODE -ne 0) {
    Write-Host "Deploy basarisiz!" -ForegroundColor Red
    exit 1
}

Write-Host "`n============================================" -ForegroundColor Green
Write-Host " DEPLOY BASARILI!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host 'Test: agentcore invoke ''{"prompt": "kritik stoklari goster"}'''
