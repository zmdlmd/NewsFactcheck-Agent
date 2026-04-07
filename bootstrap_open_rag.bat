@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0bootstrap_open_rag.ps1" %*
if errorlevel 1 pause
