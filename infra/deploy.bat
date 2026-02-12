@echo off
REM ============================================================
REM AgentCore Deploy Script - Depo Stok Yonetim Sistemi
REM CMD - Windows
REM ============================================================
REM
REM Kullanim:
REM   infra\deploy.bat
REM
REM Onkosul:
REM   - AWS CLI kurulu ve credentials ayarli
REM   - pip install bedrock-agentcore-starter-toolkit
REM   - set AWS_DEFAULT_REGION=us-west-2
REM ============================================================

setlocal enabledelayedexpansion

if "%AWS_DEFAULT_REGION%"=="" set AWS_DEFAULT_REGION=us-west-2
set REGION=%AWS_DEFAULT_REGION%
set ROLE_NAME=BedrockAgentCore-WarehouseStockMgmt-ExecutionRole
set POLICY_NAME=BedrockAgentCore-WarehouseStockMgmt-Policy

echo ============================================
echo  AgentCore Deploy - Depo Stok Yonetim
echo  Region: %REGION%
echo ============================================

REM 1. AWS kimlik kontrolu
echo.
echo [1/5] AWS kimlik kontrolu...
for /f "tokens=*" %%i in ('aws sts get-caller-identity --query Account --output text') do set ACCOUNT_ID=%%i
if "%ACCOUNT_ID%"=="" (
    echo   HATA: AWS credentials ayarli degil!
    exit /b 1
)
echo   Account: %ACCOUNT_ID%

REM 2. IAM Role olustur
echo.
echo [2/5] IAM Execution Role olusturuluyor...
aws iam get-role --role-name %ROLE_NAME% >nul 2>&1
if %errorlevel%==0 (
    echo   Role zaten mevcut: %ROLE_NAME%
) else (
    echo   Yeni role olusturuluyor: %ROLE_NAME%
    aws iam create-role --role-name %ROLE_NAME% --assume-role-policy-document file://infra/agentcore_trust_policy.json --description "AgentCore execution role for Warehouse Stock Management System" --output json
    if %errorlevel% neq 0 (
        echo   HATA: Role olusturulamadi!
        exit /b 1
    )
    echo   Role olusturuldu.
)

REM 3. Policy ekle
echo.
echo [3/5] IAM Policy ekleniyor...
aws iam put-role-policy --role-name %ROLE_NAME% --policy-name %POLICY_NAME% --policy-document file://infra/agentcore_execution_policy.json
if %errorlevel% neq 0 (
    echo   HATA: Policy eklenemedi!
    exit /b 1
)
echo   Policy eklendi: %POLICY_NAME%

set ROLE_ARN=arn:aws:iam::%ACCOUNT_ID%:role/%ROLE_NAME%
echo   Role ARN: %ROLE_ARN%

echo   IAM propagation icin 10 saniye bekleniyor...
timeout /t 10 /nobreak >nul

REM 4. AgentCore configure
echo.
echo [4/5] AgentCore configure...
agentcore configure -e agentcore_app.py -r %REGION% --execution-role %ROLE_ARN% --non-interactive
if %errorlevel% neq 0 (
    echo   HATA: AgentCore configure basarisiz!
    exit /b 1
)
echo   Configure tamamlandi.

REM 5. AgentCore deploy
echo.
echo [5/5] AgentCore deploy baslatiliyor...
echo   Bu islem birkac dakika surebilir...
agentcore deploy
if %errorlevel% neq 0 (
    echo   HATA: Deploy basarisiz!
    echo   Loglari kontrol edin: agentcore status
    exit /b 1
)

echo.
echo ============================================
echo  DEPLOY BASARILI!
echo ============================================
echo.
echo Test etmek icin:
echo   agentcore invoke "{\"prompt\": \"kritik stoklari goster\"}"
echo.
echo Durum kontrolu:
echo   agentcore status
echo.
echo Temizlik:
echo   agentcore destroy
echo   aws iam delete-role-policy --role-name %ROLE_NAME% --policy-name %POLICY_NAME%
echo   aws iam delete-role --role-name %ROLE_NAME%
