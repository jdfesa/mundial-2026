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
_dir_base_raw = os.path.expanduser(
    os.getenv("MUNDIAL_DIRECTORIO_BASE", "./Mundial_Partidos")
)
# Rutas relativas se resuelven respecto al directorio del proyecto
if not os.path.isabs(_dir_base_raw):
    _dir_base_raw = os.path.join(DIRECTORIO_PROYECTO, _dir_base_raw)
DIRECTORIO_BASE = os.path.abspath(_dir_base_raw)
ARCHIVO_CALENDARIO = os.path.join(DIRECTORIO_PROYECTO, "calendario_mundial_2026.json")
ARCHIVO_LOG = os.path.join(DIRECTORIO_PROYECTO, "mundial.log")
ARCHIVO_ESTADO = os.path.join(DIRECTORIO_PROYECTO, "estado_descargas.json")
ARCHIVO_ESTADO_TXT = os.path.join(DIRECTORIO_PROYECTO, "estado_partidos.txt")
ARCHIVO_REPORTE_DIARIO = os.path.join(DIRECTORIO_PROYECTO, "reporte_diario.txt")
ARCHIVO_FUENTES_MANUALES = os.path.join(DIRECTORIO_PROYECTO, "fuentes_manuales.json")
ARCHIVO_FUENTES_TORRENT = os.path.join(DIRECTORIO_PROYECTO, "fuentes_torrent.json")
ARCHIVO_INDICE_HTML = os.path.join(DIRECTORIO_BASE, "index.html")
ARCHIVO_PLAYLIST_M3U = os.path.join(DIRECTORIO_BASE, "playlist_mundial.m3u")
DIRECTORIOS_VERIFICACION_EXTRA = [
    p for p in os.getenv("MUNDIAL_DIRECTORIOS_EXTRA", "").split(os.pathsep) if p
]

# ─── qBittorrent ─────────────────────────────────────────────────────────────
QBIT_HOST = os.getenv("QBIT_HOST", "127.0.0.1")
QBIT_PORT = int(os.getenv("QBIT_PORT", "8080"))
QBIT_USER = os.getenv("QBIT_USER", "admin")
QBIT_PASS = os.getenv("QBIT_PASS", "adminadmin")
QBIT_CATEGORIA = "Mundial2026"
QBIT_MOVER_COMPLETADOS = os.getenv("QBIT_MOVER_COMPLETADOS", "1") not in {"0", "false", "False"}
QBIT_BUSCAR_TODAS_LAS_DESCARGAS = (
    os.getenv("QBIT_BUSCAR_TODAS_LAS_DESCARGAS", "1") not in {"0", "false", "False"}
)

# ─── Tiempos ─────────────────────────────────────────────────────────────────
# Horas de espera después de que EMPIEZA el partido antes de buscar
HORAS_ESPERA_POST_PARTIDO = 3
# Máximo de intentos de búsqueda por partido
MAX_INTENTOS = 15
# Minutos entre reintentos cuando un partido no se encuentra
MINUTOS_ENTRE_REINTENTOS = 30
# Minutos entre busquedas de mejora para partidos ya descargados en otro idioma
MINUTOS_ENTRE_REINTENTOS_MEJORA = 180
# Minutos desde que se encola una descarga hasta la primera revision esperada.
DESCARGA_REVISAR_DESPUES_MINUTOS = int(os.getenv("DESCARGA_REVISAR_DESPUES_MINUTOS", "60"))
# El fallback de yt-dlp es propenso a traer comentarios/reacciones. Se espera
# mucho mas que los torrents antes de permitirlo.
YTDLP_HORAS_ESPERA_POST_PARTIDO = int(os.getenv("YTDLP_HORAS_ESPERA_POST_PARTIDO", "24"))

# ─── Filtros de Búsqueda ─────────────────────────────────────────────────────
MIN_SEEDERS = 1  # Bajo para torrents recién subidos del mundial
TAMANO_MIN_GB = 0.5   # Mínimo 500MB (podría ser 720p comprimido)
TAMANO_MAX_GB = 10.0   # Máximo absoluto antes de penalizar fuerte
TAMANO_IDEAL_MAX_GB = 5.0
POSTPROCESO_UMBRAL_GB = 5.0
ALTURA_PREFERIDA = 720
RENOMBRAR_ARCHIVOS_CANONICOS = (
    os.getenv("MUNDIAL_RENOMBRAR_ARCHIVOS", "1") not in {"0", "false", "False"}
)
RENOMBRAR_PROVEEDORES_FILESYSTEM = {"manual", "manual_estado", "yt-dlp"}
IDIOMA_PREFERIDO = "español"
IDIOMAS_FINALES = ["es"]
# Si un resultado no declara idioma, se asume ingles porque suele ser el caso en
# los nombres de releases encontrados hasta ahora. Cambiar a "desconocido" si
# preferis no asumir.
IDIOMA_DEFAULT_SIN_INDICADOR = "en"
PERMITIR_UPGRADE_IDIOMA = True
ZONA_HORARIA_REPORTE = os.getenv("MUNDIAL_ZONA_HORARIA", "America/Argentina/Buenos_Aires")
EXTENSIONES_VIDEO = [".mp4", ".mkv", ".avi", ".mov", ".m4v", ".ts", ".webm"]

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
    "torrentgalaxy": True,
    "limetorrents": True,
    "btdig": True,  # Motor de búsqueda DHT, no requiere tracker
    "yt_dlp": True,  # Fallback con yt-dlp (YouTube, Dailymotion, etc.)
}

# ─── Groq / asistente opcional ──────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_HABILITADO = (
    bool(GROQ_API_KEY)
    and os.getenv("GROQ_HABILITADO", "1") not in {"0", "false", "False"}
)
GROQ_TIMEOUT_SEGUNDOS = int(os.getenv("GROQ_TIMEOUT_SEGUNDOS", "20"))
GROQ_MAX_QUERIES = int(os.getenv("GROQ_MAX_QUERIES", "6"))
GROQ_MAX_RESULTADOS_CLASIFICAR = int(os.getenv("GROQ_MAX_RESULTADOS_CLASIFICAR", "12"))
GROQ_GENERAR_QUERIES = (
    os.getenv("GROQ_GENERAR_QUERIES", "1") not in {"0", "false", "False"}
)
GROQ_CLASIFICAR_RESULTADOS = (
    os.getenv("GROQ_CLASIFICAR_RESULTADOS", "1") not in {"0", "false", "False"}
)


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
YTDLP_DURACION_MAXIMA = int(os.getenv("YTDLP_DURACION_MAXIMA", str(3 * 3600)))
YTDLP_ALTURA_MINIMA = int(os.getenv("YTDLP_ALTURA_MINIMA", str(ALTURA_PREFERIDA)))
YTDLP_RESULTADOS_BUSQUEDA = int(os.getenv("YTDLP_RESULTADOS_BUSQUEDA", "5"))
YTDLP_FORMATO = (
    f"bestvideo[height>={YTDLP_ALTURA_MINIMA}][height<={ALTURA_PREFERIDA}][ext=mp4]+bestaudio[ext=m4a]/"
    f"best[height>={YTDLP_ALTURA_MINIMA}][height<={ALTURA_PREFERIDA}][ext=mp4]/"
    f"best[height>={YTDLP_ALTURA_MINIMA}][height<={ALTURA_PREFERIDA}]"
)
YTDLP_TIMEOUT_SEGUNDOS = 7200
YTDLP_EXTRA_ARGS = []
YTDLP_KEYWORDS_NEGATIVAS = [
    "commentary",
    "comentarios",
    "watchalong",
    "watch along",
    "reaction",
    "reaccion",
    "reacción",
    "analisis",
    "análisis",
    "debate",
    "preview",
    "post match",
    "pre match",
    "simulation",
    "simulacion",
    "simulación",
    "gameplay",
    "ea fc",
    "fifa 26",
]
