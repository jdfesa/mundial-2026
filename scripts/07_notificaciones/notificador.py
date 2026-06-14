"""
Notificador de macOS para el Descargador de Partidos del Mundial 2026.
Usa osascript para enviar notificaciones nativas del sistema.
"""
import subprocess
import logging
import platform

logger = logging.getLogger("mundial")


def notificar(titulo: str, mensaje: str, sonido: str = "Glass"):
    """Envía una notificación nativa si el sistema lo permite."""
    if platform.system().lower() != "darwin":
        logger.info(f"Notificación omitida en este sistema: {titulo} - {mensaje}")
        return

    try:
        script = f'''
        display notification "{mensaje}" with title "{titulo}" sound name "{sonido}"
        '''
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10
        )
        logger.info(f"Notificación enviada: {titulo} - {mensaje}")
    except Exception as e:
        logger.warning(f"No se pudo enviar notificación: {e}")


def notificar_descarga_iniciada(equipo1: str, equipo2: str):
    """Notifica que se inició la descarga de un partido."""
    notificar(
        "⚽ Mundial 2026 - Descarga Iniciada",
        f"{equipo1} vs {equipo2} se está descargando...",
        "Submarine"
    )


def notificar_descarga_completada(equipo1: str, equipo2: str):
    """Notifica que se completó la descarga de un partido."""
    notificar(
        "✅ Mundial 2026 - Descarga Completa",
        f"¡{equipo1} vs {equipo2} listo para ver!",
        "Hero"
    )


def notificar_no_encontrado(equipo1: str, equipo2: str, intentos: int):
    """Notifica que no se encontró un partido después de varios intentos."""
    notificar(
        "⚠️ Mundial 2026 - No Encontrado",
        f"{equipo1} vs {equipo2} no se encontró (intento {intentos}). Se reintentará.",
        "Basso"
    )


def notificar_qbittorrent_necesario():
    """Notifica que se necesita abrir qBittorrent."""
    notificar(
        "🔧 Mundial 2026 - qBittorrent Requerido",
        "Se necesita qBittorrent abierto. Intentando abrirlo automáticamente...",
        "Ping"
    )


def notificar_error(mensaje: str):
    """Notifica un error general."""
    notificar(
        "❌ Mundial 2026 - Error",
        mensaje,
        "Basso"
    )


def notificar_resumen(descargados: int, fallidos: int, pendientes: int):
    """Notifica un resumen de la ejecución."""
    notificar(
        "📊 Mundial 2026 - Resumen",
        f"Descargados: {descargados} | Fallidos: {fallidos} | Pendientes: {pendientes}",
        "Glass"
    )
