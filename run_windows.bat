@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PYTHON_BIN=%SCRIPT_DIR%venv\Scripts\python.exe"

if not exist "%PYTHON_BIN%" (
  set "PYTHON_BIN=python"
)

cd /d "%SCRIPT_DIR%"
"%PYTHON_BIN%" "%SCRIPT_DIR%descargar_partidos.py" %*

endlocal
