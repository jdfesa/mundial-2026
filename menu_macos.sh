#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNNER="$SCRIPT_DIR/run_macos.sh"
PYTHON_BIN="$SCRIPT_DIR/venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

cd "$SCRIPT_DIR"

pausa() {
  printf "\nPresiona Enter para volver al menu..."
  read -r _
}

titulo() {
  printf "\n"
  printf "============================================================\n"
  printf " Mundial 2026 - Menu macOS\n"
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

instalar_launchd() {
  printf "Esto instalara/actualizara la tarea automatica cada 30 min. Continuar? [s/N]: "
  read -r respuesta
  case "$respuesta" in
    s|S|si|SI)
      "$SCRIPT_DIR/install_macos_launchd.sh"
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
  printf "  8) Instalar/actualizar tarea automatica macOS\n"
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
      instalar_launchd
      pausa
      ;;
    9)
      if [ -f "$SCRIPT_DIR/reporte_diario.txt" ]; then
        sed -n '1,120p' "$SCRIPT_DIR/reporte_diario.txt"
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
