@echo off
setlocal

set "UTIL_DIR=%~dp0"
set "TASK_NAME=Mundial2026Descargador"
set "RUNNER=%UTIL_DIR%run_windows.bat"

if not exist "%RUNNER%" (
  echo No se encontro %RUNNER%
  exit /b 1
)

schtasks /Create /TN "%TASK_NAME%" /SC MINUTE /MO 30 /TR "\"%RUNNER%\"" /F

echo Tarea instalada: %TASK_NAME%
echo Se ejecutara cada 30 minutos y el script decidira que partidos ya estan listos.

endlocal
