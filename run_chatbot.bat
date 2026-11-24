@echo off
title Universal AI Chatbot Platform
echo ========================================================
echo Starting Universal AI Chatbot Platform...
echo ========================================================
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Using Python: %PYTHON_EXE%
echo API Server:  http://localhost:8080
echo Demo Widget: http://localhost:8080/demo
echo API Docs:    http://localhost:8080/docs
echo ========================================================

%PYTHON_EXE% -m uvicorn universal_chatbot.backend.app.main:app --host 0.0.0.0 --port 8080 --reload
pause
