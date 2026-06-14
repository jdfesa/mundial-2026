#!/usr/bin/env bash
set -euo pipefail

UTIL_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$UTIL_DIR/../.." && pwd)"
RUNNER="$PROJECT_ROOT/run.sh"
PYTHON_BIN="$PROJECT_ROOT/venv/bin/python"
SCRIPTS_DIR="$PROJECT_ROOT/scripts"
SISTEMA="$(uname -s)"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

MUNDIAL_PYTHONPATH="$SCRIPTS_DIR"
for dir in "$SCRIPTS_DIR"/[0-9][0-9]_*; do
  if [ -d "$dir" ]; then
    MUNDIAL_PYTHONPATH="$MUNDIAL_PYTHONPATH:$dir"
  fi
done
export PYTHONPATH="$MUNDIAL_PYTHONPATH${PYTHONPATH:+:$PYTHONPATH}"

cd "$PROJECT_ROOT"

pausa() {
  printf "\nPresiona Enter para volver al menu..."
  read -r _
}

titulo() {
  printf "\n"
  printf "============================================================\n"
  printf " Mundial 2026 - Menu (%s)\n" "$SISTEMA"
  printf "============================================================\n"
}

mostrar_rutas() {
  "$PYTHON_BIN" -c 'import config; print("Proyecto:", config.DIRECTORIO_PROYECTO); print("Destino:", config.DIRECTORIO_BASE); print("Estado:", config.ARCHIVO_ESTADO_TXT); print("Reporte:", config.ARCHIVO_REPORTE_DIARIO); print("Indice:", config.ARCHIVO_INDICE_HTML); print("Playlist:", config.ARCHIVO_PLAYLIST_M3U)'
}

probar_qbit() {
  printf "\nProbando Web UI en http://127.0.0.1:8080 ...\n"
  if command -v curl >/dev/null 2>&1; then
    code="$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080 || true)"
    printf "HTTP status: %s\n" "$code"
    case "$code" in
      200|401|403)
        printf "Web UI responde.\n"
        ;;
      000)
        printf "No responde. Revisar Web UI, IP 127.0.0.1, puerto 8080 y Apply/OK.\n"
        ;;
      *)
        printf "Respuesta inesperada; puede estar levantada igual.\n"
        ;;
    esac
  else
    printf "curl no esta disponible.\n"
  fi

  printf "\nProbando API con usuario/password del .env ...\n"
  "$PYTHON_BIN" -c 'from qbit_manager import obtener_cliente; c=obtener_cliente(abrir_si_no_corre=False); print("API OK" if c else "API no disponible o credenciales invalidas")'
}

marcar_descargado() {
  printf "ID del partido: "
  read -r id
  printf "Idioma (es/en/desconocido) [en]: "
  read -r idioma
  idioma="${idioma:-en}"
  printf "Titulo/archivo visto en qBittorrent: "
  read -r archivo

  if [ -z "$id" ] || [ -z "$archivo" ]; then
    printf "Falta ID o titulo. No se marco nada.\n"
    return
  fi

  "$RUNNER" --marcar-descargado "$id" --idioma "$idioma" --archivo "$archivo"
}

forzar_partido() {
  printf "ID del partido a forzar: "
  read -r id
  if [ -z "$id" ]; then
    printf "Falta ID. No se ejecuto nada.\n"
    return
  fi
  "$RUNNER" --forzar "$id"
}

instalar_automatizacion() {
  if [ "$SISTEMA" != "Darwin" ]; then
    printf "La instalacion automatica incluida es solo para macOS/launchd.\n"
    printf "En Linux conviene crear un cron o systemd timer que ejecute:\n"
    printf "  %s\n" "$RUNNER"
    printf "En Windows usar scripts\\90_utilidades\\install_windows_task.bat desde PowerShell/CMD.\n"
    return
  fi

  printf "Esto instalara/actualizara la tarea automatica cada 30 min. Continuar? [s/N]: "
  read -r respuesta
  case "$respuesta" in
    s|S|si|SI)
      "$UTIL_DIR/install_macos_launchd.sh"
      ;;
    *)
      printf "Cancelado.\n"
      ;;
  esac
}

while true; do
  titulo
  mostrar_rutas
  printf "\nOpciones:\n"
  printf "  1) Ver estado completo\n"
  printf "  2) Ejecutar ahora (busca y encola descargas)\n"
  printf "  3) Simular ejecucion (dry-run)\n"
  printf "  4) Simular solo fuentes manuales\n"
  printf "  5) Forzar partido por ID\n"
  printf "  6) Marcar partido como descargado\n"
  printf "  7) Probar qBittorrent Web UI/API\n"
  printf "  8) Automatizacion del sistema\n"
  printf "  9) Mostrar reporte diario\n"
  printf "  0) Salir\n"
  printf "\nElegir opcion: "
  read -r opcion

  case "$opcion" in
    1)
      "$RUNNER" --status
      pausa
      ;;
    2)
      "$RUNNER"
      pausa
      ;;
    3)
      "$RUNNER" --dry-run
      pausa
      ;;
    4)
      "$RUNNER" --dry-run --solo-manuales
      pausa
      ;;
    5)
      forzar_partido
      pausa
      ;;
    6)
      marcar_descargado
      pausa
      ;;
    7)
      probar_qbit
      pausa
      ;;
    8)
      instalar_automatizacion
      pausa
      ;;
    9)
      if [ -f "$PROJECT_ROOT/reporte_diario.txt" ]; then
        sed -n '1,120p' "$PROJECT_ROOT/reporte_diario.txt"
      else
        printf "No existe reporte_diario.txt todavia. Ejecuta --status primero.\n"
      fi
      pausa
      ;;
    0)
      exit 0
      ;;
    *)
      printf "Opcion invalida.\n"
      pausa
      ;;
  esac
done
