@echo off
setlocal

set "UTIL_DIR=%~dp0"
for %%I in ("%UTIL_DIR%..\..") do set "PROJECT_ROOT=%%~fI"
set "PYTHON_BIN=%PROJECT_ROOT%\venv\Scripts\python.exe"

if not exist "%PYTHON_BIN%" (
  set "PYTHON_BIN=python"
)

cd /d "%PROJECT_ROOT%"
"%PYTHON_BIN%" "%PROJECT_ROOT%\scripts\00_orquestador\descargar_partidos.py" %*

endlocal
