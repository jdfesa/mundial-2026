"""
Configuración centralizada del Descargador de Partidos - Mundial 2026

Lee datos locales desde el archivo .env (rutas, credenciales).
Si no existe .env, usa valores por defecto razonables.
"""
import json
import os

DIRECTORIO_PROYECTO = os.path.dirname(os.path.abspath(__file__))


# ─── Loader de .env (sin dependencias externas) ─────────────────────────────

def _cargar_env(ruta: str | None = None) -> None:
    """Lee un archivo .env y carga las variables en os.environ."""
    ruta = ruta or os.path.join(DIRECTORIO_PROYECTO, ".env")
    if not os.path.exists(ruta):
        return
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            if "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            clave = clave.strip()
            valor = valor.strip().strip('"').strip("'")
            if clave and clave not in os.environ:
                os.environ[clave] = valor


_cargar_env()


# ─── Rutas ───────────────────────────────────────────────────────────────────
DIRECTORIO_BASE = os.path.expanduser(
    os.getenv("MUNDIAL_DIRECTORIO_BASE", "~/Desktop/Mundial_Partidos")
)
ARCHIVO_CALENDARIO = os.path.join(DIRECTORIO_PROYECTO, "calendario_mundial_2026.json")
ARCHIVO_LOG = os.path.join(DIRECTORIO_PROYECTO, "mundial.log")
ARCHIVO_ESTADO = os.path.join(DIRECTORIO_PROYECTO, "estado_descargas.json")
ARCHIVO_ESTADO_TXT = os.path.join(DIRECTORIO_PROYECTO, "estado_partidos.txt")
ARCHIVO_FUENTES_MANUALES = os.path.join(DIRECTORIO_PROYECTO, "fuentes_manuales.json")
ARCHIVO_FUENTES_TORRENT = os.path.join(DIRECTORIO_PROYECTO, "fuentes_torrent.json")

# ─── qBittorrent ─────────────────────────────────────────────────────────────
QBIT_HOST = os.getenv("QBIT_HOST", "127.0.0.1")
QBIT_PORT = int(os.getenv("QBIT_PORT", "8080"))
QBIT_USER = os.getenv("QBIT_USER", "admin")
QBIT_PASS = os.getenv("QBIT_PASS", "adminadmin")
QBIT_CATEGORIA = "Mundial2026"

# ─── Tiempos ─────────────────────────────────────────────────────────────────
# Horas de espera después de que EMPIEZA el partido antes de buscar
HORAS_ESPERA_POST_PARTIDO = 3
# Máximo de intentos de búsqueda por partido
MAX_INTENTOS = 15
# Minutos entre reintentos cuando un partido no se encuentra
MINUTOS_ENTRE_REINTENTOS = 30

# ─── Filtros de Búsqueda ─────────────────────────────────────────────────────
MIN_SEEDERS = 1  # Bajo para torrents recién subidos del mundial
TAMANO_MIN_GB = 0.5   # Mínimo 500MB (podría ser 720p comprimido)
TAMANO_MAX_GB = 10.0   # Máximo 10GB
IDIOMA_PREFERIDO = "español"
IDIOMAS_FINALES = ["es"]
# Si un resultado no declara idioma, se asume ingles porque suele ser el caso en
# los nombres de releases encontrados hasta ahora. Cambiar a "desconocido" si
# preferis no asumir.
IDIOMA_DEFAULT_SIN_INDICADOR = "en"
PERMITIR_UPGRADE_IDIOMA = True

# Palabras clave para buscar partidos completos (no resúmenes)
KEYWORDS_POSITIVAS = [
    "completo", "full match", "full game", "partido completo",
    "1080p", "720p", "hdtv", "hd", "full hd",
    "español", "spanish", "espanol", "latino",
    "relato", "castellano"
]

# Excluir estos resultados
KEYWORDS_NEGATIVAS = [
    "highlights", "resumen", "goles", "goals only",
    "best moments", "mejores momentos", "preview",
    "promo", "trailer", "reaction", "reaccion"
]

# ─── Prioridad de Equipos ────────────────────────────────────────────────────
# Los partidos de estos equipos tienen prioridad "alta"
EQUIPOS_FAVORITOS = ["Argentina"]

# ─── Estructura de Carpetas por Fase ─────────────────────────────────────────
CARPETAS_FASE = {
    "grupo": "Fase_de_Grupos",
    "octavos": "Octavos_de_Final",
    "cuartos": "Cuartos_de_Final",
    "semifinal": "Semifinales",
    "tercer_puesto": "Tercer_Puesto",
    "final": "Final"
}

# ─── Fuentes de Búsqueda ─────────────────────────────────────────────────────
# Habilitar/deshabilitar fuentes (se puede sobreescribir desde fuentes_torrent.json)
FUENTES_HABILITADAS = {
    "manuales": True,  # URLs declaradas por vos en fuentes_manuales.json
    "1337x": True,
    "piratebay": True,
    "yt_dlp": True,  # Fallback con yt-dlp (YouTube, Dailymotion, etc.)
}


def cargar_fuentes_torrent() -> dict:
    """
    Carga la configuración de indexadores desde fuentes_torrent.json.
    Retorna un dict con los indexadores y sus mirrors.
    """
    if not os.path.exists(ARCHIVO_FUENTES_TORRENT):
        return {"indexadores": []}
    try:
        with open(ARCHIVO_FUENTES_TORRENT, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"indexadores": []}


def obtener_mirrors_tpb() -> list[str]:
    """Retorna los mirrors de TPB desde fuentes_torrent.json."""
    datos = cargar_fuentes_torrent()
    for idx in datos.get("indexadores", []):
        if idx.get("nombre") == "piratebay" and idx.get("habilitado"):
            return idx.get("mirrors", [])
    return []


def indexador_habilitado(nombre: str) -> bool:
    """Verifica si un indexador está habilitado en fuentes_torrent.json."""
    datos = cargar_fuentes_torrent()
    for idx in datos.get("indexadores", []):
        if idx.get("nombre") == nombre:
            return idx.get("habilitado", False)
    # Fallback a FUENTES_HABILITADAS
    return FUENTES_HABILITADAS.get(nombre, False)


# ─── yt-dlp (fallback) ──────────────────────────────────────────────────────
YTDLP_DURACION_MINIMA = 5400  # 90 minutos en segundos
YTDLP_FORMATO = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
YTDLP_TIMEOUT_SEGUNDOS = 7200
YTDLP_EXTRA_ARGS = []
