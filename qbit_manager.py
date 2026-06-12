"""
Gestor de qBittorrent para el Descargador de Partidos del Mundial 2026.
Maneja la conexión, envío de torrents y monitoreo de descargas.
"""
import subprocess
import time
import logging
import os
import platform
import config

logger = logging.getLogger("mundial")

# Se importa condicionalmente para manejar el caso donde no esté instalado
try:
    import qbittorrentapi
    QBIT_DISPONIBLE = True
except ImportError:
    QBIT_DISPONIBLE = False
    logger.warning("qbittorrent-api no está instalado. Ejecutá: pip install qbittorrent-api")


def esta_qbittorrent_corriendo() -> bool:
    """Verifica si qBittorrent está corriendo."""
    try:
        sistema = platform.system().lower()
        if sistema == "windows":
            resultado = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq qbittorrent.exe"],
                capture_output=True, text=True
            )
            return "qbittorrent.exe" in resultado.stdout.lower()

        nombres = ["qBittorrent", "qbittorrent"]
        for nombre in nombres:
            resultado = subprocess.run(
                ["pgrep", "-x", nombre],
                capture_output=True, text=True
            )
            if resultado.returncode == 0:
                return True
            if sistema == "darwin" and resultado.returncode not in (0, 1):
                break

        if sistema == "darwin":
            resultado = subprocess.run(
                ["osascript", "-e", 'application "qBittorrent" is running'],
                capture_output=True, text=True, timeout=5
            )
            if resultado.returncode == 0:
                return resultado.stdout.strip().lower() == "true"
        return False
    except Exception:
        return False


def abrir_qbittorrent() -> bool:
    """Intenta abrir qBittorrent según el sistema operativo."""
    try:
        sistema = platform.system().lower()
        if sistema == "darwin":
            resultado = subprocess.run(
                ["open", "-a", "qBittorrent"],
                capture_output=True, text=True, timeout=10
            )
        elif sistema == "windows":
            candidatos = [
                os.path.join(os.environ.get("ProgramFiles", ""), "qBittorrent", "qbittorrent.exe"),
                os.path.join(os.environ.get("ProgramFiles(x86)", ""), "qBittorrent", "qbittorrent.exe"),
            ]
            ejecutable = next((c for c in candidatos if c and os.path.exists(c)), None)
            if ejecutable:
                subprocess.Popen([ejecutable])
            else:
                subprocess.Popen(["cmd", "/c", "start", "", "qbittorrent"])
            logger.info("qBittorrent abierto exitosamente. Esperando 5 segundos...")
            time.sleep(5)
            return True
        else:
            resultado = subprocess.run(
                ["qbittorrent"],
                capture_output=True, text=True, timeout=10
            )

        if resultado.returncode == 0:
            logger.info("qBittorrent abierto exitosamente. Esperando 5 segundos...")
            time.sleep(5)  # Darle tiempo a que arranque la Web UI
            return True
        else:
            logger.error(f"No se pudo abrir qBittorrent: {resultado.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error al intentar abrir qBittorrent: {e}")
        return False


def obtener_cliente(abrir_si_no_corre: bool = True):
    """
    Obtiene un cliente conectado de qBittorrent.
    Si qBittorrent no está corriendo, intenta abrirlo.
    Retorna el cliente o None si falla.
    """
    if not QBIT_DISPONIBLE:
        logger.error("qbittorrent-api no está instalado")
        return None

    # Verificar si está corriendo, si no, intentar abrirlo
    if not esta_qbittorrent_corriendo():
        if not abrir_si_no_corre:
            logger.info("qBittorrent no está corriendo; se omite consulta de estado")
            return None

        from notificador import notificar_qbittorrent_necesario
        notificar_qbittorrent_necesario()

        if not abrir_qbittorrent():
            logger.error("No se pudo iniciar qBittorrent")
            return None

        # Esperar un poco más para que la Web UI esté lista
        time.sleep(3)

    # Intentar conectar
    cliente = qbittorrentapi.Client(
        host=config.QBIT_HOST,
        port=config.QBIT_PORT,
        username=config.QBIT_USER,
        password=config.QBIT_PASS,
    )

    try:
        cliente.auth_log_in()
        logger.info(f"Conectado a qBittorrent v{cliente.app.version}")
        return cliente
    except qbittorrentapi.LoginFailed as e:
        logger.error(f"Error de autenticación en qBittorrent: {e}")
        logger.error("Verificá que la Web UI esté habilitada y las credenciales sean correctas")
        return None
    except Exception as e:
        logger.error(f"Error conectando a qBittorrent: {e}")
        return None


def enviar_magnet(magnet_link: str, carpeta_destino: str, nombre_partido: str) -> bool:
    """
    Envía un magnet link a qBittorrent para descarga.
    Intenta primero via Web API, y si falla usa `open` de macOS como fallback.
    
    Args:
        magnet_link: El magnet link del torrent
        carpeta_destino: Ruta absoluta de la carpeta de destino
        nombre_partido: Nombre descriptivo del partido (para logging)
    
    Returns:
        True si se envió exitosamente, False en caso contrario
    """
    # Intentar via Web API primero
    cliente = obtener_cliente()
    if cliente:
        try:
            # Crear la categoría si no existe
            try:
                cliente.torrents_create_category(
                    name=config.QBIT_CATEGORIA,
                    save_path=config.DIRECTORIO_BASE
                )
            except Exception:
                pass  # La categoría ya existe

            # Enviar el torrent
            resultado = cliente.torrents_add(
                urls=magnet_link,
                save_path=carpeta_destino,
                category=config.QBIT_CATEGORIA,
                rename=nombre_partido
            )

            if resultado == "Ok.":
                logger.info(f"Torrent enviado a qBittorrent via API: {nombre_partido}")
                logger.info(f"  Carpeta destino: {carpeta_destino}")
                return True
            else:
                logger.warning(f"qBittorrent API respondió: {resultado}")
        except Exception as e:
            logger.warning(f"Error con API de qBittorrent: {e}")

    # ── FALLBACK: abrir magnet link directamente con el sistema ──
    # Esto abre el magnet en qBittorrent sin necesitar la Web UI
    logger.info("Usando fallback: abriendo magnet link directamente en qBittorrent...")

    # Asegurar que qBittorrent esté abierto
    if not esta_qbittorrent_corriendo():
        abrir_qbittorrent()

    try:
        sistema = platform.system().lower()
        if sistema == "darwin":
            resultado = subprocess.run(
                ["open", magnet_link],
                capture_output=True, text=True, timeout=15
            )
            exito_open = resultado.returncode == 0
            stderr = resultado.stderr
        elif sistema == "windows":
            resultado = subprocess.run(
                ["cmd", "/c", "start", "", magnet_link],
                capture_output=True, text=True, timeout=15
            )
            exito_open = resultado.returncode == 0
            stderr = resultado.stderr
        else:
            resultado = subprocess.run(
                ["xdg-open", magnet_link],
                capture_output=True, text=True, timeout=15
            )
            exito_open = resultado.returncode == 0
            stderr = resultado.stderr

        if exito_open:
            logger.info(f"✅ Magnet link abierto en qBittorrent: {nombre_partido}")
            logger.info(f"   ⚠️  Nota: La carpeta de destino deberá configurarse manualmente")
            logger.info(f"   Recomendado: {carpeta_destino}")
            return True
        else:
            logger.error(f"Error abriendo magnet link: {stderr}")
            return False
    except Exception as e:
        logger.error(f"Error en fallback de magnet link: {e}")
        return False


def verificar_estado_descarga(nombre_partido: str) -> dict | None:
    """
    Verifica el estado de descarga de un partido.
    
    Returns:
        Diccionario con info del torrent o None si no se encuentra
    """
    cliente = obtener_cliente()
    if not cliente:
        return None

    try:
        torrents = cliente.torrents_info(category=config.QBIT_CATEGORIA)
        for torrent in torrents:
            if nombre_partido.lower() in torrent.name.lower():
                return {
                    "nombre": torrent.name,
                    "progreso": round(torrent.progress * 100, 1),
                    "estado": torrent.state,
                    "tamano": round(torrent.size / (1024**3), 2),  # GB
                    "velocidad": round(torrent.dlspeed / (1024**2), 2),  # MB/s
                    "ruta": torrent.save_path,
                    "completado": torrent.progress >= 1.0
                }
    except Exception as e:
        logger.error(f"Error verificando estado de descarga: {e}")

    return None


def _torrent_attr(torrent, nombre: str, default=None):
    """Lee atributos de qbittorrent-api soportando dicts y objetos."""
    if isinstance(torrent, dict):
        return torrent.get(nombre, default)
    return getattr(torrent, nombre, default)


def listar_torrents(incluir_todos: bool = False, iniciar_si_no_corre: bool = False) -> list[dict]:
    """Lista torrents con metadata suficiente para sincronizar carpetas."""
    cliente = obtener_cliente(abrir_si_no_corre=iniciar_si_no_corre)
    if not cliente:
        return []

    try:
        if incluir_todos:
            torrents = cliente.torrents_info()
        else:
            torrents = cliente.torrents_info(category=config.QBIT_CATEGORIA)

        resultado = []
        for torrent in torrents:
            progreso = float(_torrent_attr(torrent, "progress", 0) or 0)
            resultado.append({
                "hash": _torrent_attr(torrent, "hash", ""),
                "nombre": _torrent_attr(torrent, "name", ""),
                "categoria": _torrent_attr(torrent, "category", ""),
                "progreso": round(progreso * 100, 1),
                "completado": progreso >= 1.0,
                "estado": _torrent_attr(torrent, "state", ""),
                "tamano_gb": round((_torrent_attr(torrent, "size", 0) or 0) / (1024**3), 2),
                "ruta": _torrent_attr(torrent, "save_path", ""),
                "content_path": _torrent_attr(torrent, "content_path", ""),
            })
        return resultado
    except Exception as e:
        logger.error(f"Error listando torrents: {e}")
        return []


def mover_torrent(torrent_hash: str, carpeta_destino: str) -> bool:
    """
    Pide a qBittorrent que mueva el contenido de un torrent.

    Usar la API es más seguro que mover archivos con shutil mientras qBittorrent
    puede estar seedeando o manteniendo handles abiertos.
    """
    if not torrent_hash:
        return False

    cliente = obtener_cliente(abrir_si_no_corre=False)
    if not cliente:
        return False

    os.makedirs(carpeta_destino, exist_ok=True)
    try:
        resultado = cliente.torrents_set_location(
            location=carpeta_destino,
            torrent_hashes=[torrent_hash],
        )
        if resultado in (None, "Ok."):
            logger.info(f"Torrent movido por qBittorrent a: {carpeta_destino}")
            return True
        logger.warning(f"qBittorrent respondió al mover torrent: {resultado}")
        return False
    except Exception as e:
        logger.error(f"Error moviendo torrent en qBittorrent: {e}")
        return False


def listar_descargas_mundial(iniciar_si_no_corre: bool = False) -> list:
    """Lista todas las descargas de la categoría Mundial2026."""
    return listar_torrents(incluir_todos=False, iniciar_si_no_corre=iniciar_si_no_corre)
