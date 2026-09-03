@echo off
chcp 65001 >nul
title Central de Erros - Brobot

rem Garante que o diretorio atual seja a pasta onde o .bat esta localizado
cd /d "%~dp0"

echo ======================================================
echo           CENTRAL DE ERROS - BROBOT
echo ======================================================
echo.
echo [1/2] Verificando ambiente...

rem Se existir um ambiente virtual, ativa
if exist ".venv\Scripts\activate.bat" (
    echo [*] Ativando ambiente virtual .venv...
    call ".venv\Scripts\activate.bat"
)
if exist "venv\Scripts\activate.bat" (
    echo [*] Ativando ambiente virtual venv...
    call "venv\Scripts\activate.bat"
)

echo [2/2] Iniciando aplicacao Streamlit...
echo.
echo * O seu navegador padrao sera aberto automaticamente em instantes!
echo * Para encerrar a aplicacao, feche esta janela ou pressione Ctrl+C.
echo.
echo ======================================================
echo.

rem Executa o Streamlit
python -m streamlit run app.py

if errorlevel 1 (
    echo.
    echo [*] Tentando inicializar via py...
    py -m streamlit run app.py
)

if errorlevel 1 (
    echo.
    echo ======================================================
    echo [ERRO] Nao foi possivel iniciar a aplicacao.
    echo Verifique se o Python e as dependencias estao instalados:
    echo pip install -r requirements.txt
    echo ======================================================
    echo.
    pause
)
