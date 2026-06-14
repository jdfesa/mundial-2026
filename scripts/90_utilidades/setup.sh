#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# 🏆 Setup del Descargador de Partidos - Mundial FIFA 2026
# ═══════════════════════════════════════════════════════════════════════
set -e

UTIL_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$UTIL_DIR/../.." && pwd)"
VENV_DIR="$PROJECT_ROOT/venv"
RUNNER="$PROJECT_ROOT/run.sh"

if [ "$(uname -s)" != "Darwin" ]; then
    echo "Este setup automatico esta preparado para macOS/launchd."
    echo "En Linux instala dependencias con pip y ejecuta: ./run.sh --status"
    echo "Para automatizar, crea un cron o systemd timer que ejecute: $RUNNER"
    exit 1
fi

echo "🏆 Configurando Descargador de Partidos - Mundial 2026"
echo "═══════════════════════════════════════════════════════"

# 1. Crear/actualizar entorno virtual
echo ""
echo "📦 Configurando entorno virtual..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "   ✅ Entorno virtual creado"
else
    echo "   ℹ️  Entorno virtual ya existe"
fi

source "$VENV_DIR/bin/activate"

# 2. Instalar dependencias
echo ""
echo "📦 Instalando dependencias..."
pip install --upgrade pip -q
pip install -r "$PROJECT_ROOT/requirements.txt" -q
echo "   ✅ Dependencias instaladas"

# 3. Crear estructura de directorios
echo ""
echo "📁 Creando estructura de directorios..."
DESTINO="$HOME/Desktop/Mundial_Partidos"
mkdir -p "$DESTINO/Fase_de_Grupos/Grupo_A"
mkdir -p "$DESTINO/Fase_de_Grupos/Grupo_B"
mkdir -p "$DESTINO/Fase_de_Grupos/Grupo_C"
mkdir -p "$DESTINO/Fase_de_Grupos/Grupo_D"
mkdir -p "$DESTINO/Fase_de_Grupos/Grupo_E"
mkdir -p "$DESTINO/Fase_de_Grupos/Grupo_F"
mkdir -p "$DESTINO/Fase_de_Grupos/Grupo_G"
mkdir -p "$DESTINO/Fase_de_Grupos/Grupo_H"
mkdir -p "$DESTINO/Fase_de_Grupos/Grupo_I"
mkdir -p "$DESTINO/Fase_de_Grupos/Grupo_J"
mkdir -p "$DESTINO/Fase_de_Grupos/Grupo_K"
mkdir -p "$DESTINO/Fase_de_Grupos/Grupo_L"
mkdir -p "$DESTINO/Octavos_de_Final"
mkdir -p "$DESTINO/Cuartos_de_Final"
mkdir -p "$DESTINO/Semifinales"
mkdir -p "$DESTINO/Tercer_Puesto"
mkdir -p "$DESTINO/Final"
echo "   ✅ Directorios creados en $DESTINO"

# 4. Verificar calendario
echo ""
echo "📅 Verificando calendario..."
PARTIDOS=$(python3 -c "import json; d=json.load(open('$PROJECT_ROOT/calendario_mundial_2026.json')); print(len(d))")
echo "   ✅ Calendario cargado: $PARTIDOS partidos"

# 5. Verificar qBittorrent
echo ""
echo "🔧 Verificando qBittorrent..."
if pgrep -x "qbittorrent" > /dev/null 2>&1; then
    echo "   ✅ qBittorrent está corriendo"
    # Verificar Web UI
    if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8080" 2>/dev/null | grep -q "200\|401"; then
        echo "   ✅ Web UI accesible en puerto 8080"
    else
        echo "   ⚠️  Web UI no responde en puerto 8080"
        echo "   ➡️  Habilitá la Web UI: Preferencias > Web UI > Habilitar"
    fi
else
    echo "   ⚠️  qBittorrent no está corriendo"
    echo "   ➡️  Abriendo qBittorrent..."
    open -a qBittorrent 2>/dev/null || echo "   ❌ No se pudo abrir. ¿Está instalado?"
    echo "   ➡️  Asegurate de habilitar la Web UI en Preferencias"
fi

# 6. Instalar LaunchAgent
echo ""
echo "⏰ Instalando tarea programada (launchd)..."
"$UTIL_DIR/install_macos_launchd.sh"
echo "   ✅ Tarea programada instalada"

# 7. Test rápido
echo ""
echo "🧪 Ejecutando test rápido (dry-run)..."
cd "$PROJECT_ROOT"
"$RUNNER" --dry-run 2>&1 | head -20

echo ""
echo "═══════════════════════════════════════════════════════"
echo "✅ ¡Setup completado!"
echo ""
echo "Comandos útiles:"
echo "  Ver estado:        ./run.sh --status"
echo "  Ejecutar manual:   ./run.sh"
echo "  Simular:           ./run.sh --dry-run"
echo "  Forzar partido:    ./run.sh --forzar 1"
echo ""
echo "Los partidos se guardarán en: $DESTINO"
echo "═══════════════════════════════════════════════════════"
