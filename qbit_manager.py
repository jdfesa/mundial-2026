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
from pathlib import Path

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
                logger.debug(f"No se pudo consultar proceso qBittorrent con pgrep: {resultado.stderr.strip()}")
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


def _conectar_web_api(log_errores: bool = True):
    """Intenta conectar con la Web API de qBittorrent."""
    cliente = qbittorrentapi.Client(
        host=config.QBIT_HOST,
        port=config.QBIT_PORT,
        username=config.QBIT_USER,
        password=config.QBIT_PASS,
    )

    try:
        cliente.auth_log_in()
        version = str(cliente.app.version).lstrip("v")
        logger.info(f"Conectado a qBittorrent v{version}")
        return cliente, None
    except qbittorrentapi.LoginFailed as e:
        mensaje = f"Error de autenticación en qBittorrent: {e}"
        if log_errores:
            logger.error(mensaje)
            logger.error("Verificá que la Web UI esté habilitada y las credenciales sean correctas")
        return None, mensaje
    except Exception as e:
        mensaje = f"Error conectando a qBittorrent Web API ({config.QBIT_HOST}:{config.QBIT_PORT}): {e}"
        if log_errores:
            logger.error(mensaje)
        return None, mensaje


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
    Primero prueba la Web API; si no responde y está permitido, intenta abrir la app.
    Retorna el cliente o None si falla.
    """
    if not QBIT_DISPONIBLE:
        logger.error("qbittorrent-api no está instalado")
        return None

    cliente, error = _conectar_web_api(log_errores=False)
    if cliente:
        return cliente

    corriendo = esta_qbittorrent_corriendo()
    if not abrir_si_no_corre:
        logger.info(
            f"qBittorrent Web API no responde en {config.QBIT_HOST}:{config.QBIT_PORT}; "
            "se omite consulta de estado"
        )
        if corriendo:
            logger.debug("La app de qBittorrent parece estar abierta, pero la Web API no respondió")
        logger.debug(error)
        return None

    if not corriendo:
        from notificador import notificar_qbittorrent_necesario
        notificar_qbittorrent_necesario()

        if not abrir_qbittorrent():
            logger.error("No se pudo iniciar qBittorrent")
            return None

        # Esperar un poco más para que la Web UI esté lista
        time.sleep(3)

    cliente, _ = _conectar_web_api(log_errores=True)
    return cliente


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


def _extension_video(ruta_relativa: str) -> bool:
    extensiones = tuple(e.lower() for e in getattr(config, "EXTENSIONES_VIDEO", []))
    return Path(ruta_relativa).suffix.lower() in extensiones


def _extension_auxiliar_limpiable(ruta_relativa: str) -> bool:
    extensiones = getattr(config, "QBIT_EXTENSIONES_AUXILIARES", {".nfo", ".txt", ".url"})
    return Path(ruta_relativa).suffix.lower() in extensiones


def _tamano_archivo_torrent(archivo) -> int:
    valor = _torrent_attr(archivo, "size", 0)
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0


def _renombrar_archivo_relativo(cliente, torrent_hash: str, old_path: str, new_path: str) -> bool:
    """Renombra un archivo interno del torrent usando rutas relativas qBittorrent."""
    try:
        cliente.torrents_rename_file(
            torrent_hash=torrent_hash,
            old_path=old_path,
            new_path=new_path,
        )
    except TypeError:
        cliente.torrents_renameFile(
            torrent_hash=torrent_hash,
            old_path=old_path,
            new_path=new_path,
        )
    return True


def _path_seguro_en_raiz(path: Path, raiz: Path) -> bool:
    try:
        path_resuelto = path.expanduser().resolve()
        raiz_resuelta = raiz.expanduser().resolve()
    except OSError:
        return False
    try:
        return path_resuelto.is_relative_to(raiz_resuelta)
    except AttributeError:
        return str(path_resuelto).startswith(str(raiz_resuelta))


def _limpiar_directorios_vacios(path: Path, raiz: Path) -> None:
    """Borra carpetas vacias hasta llegar a la raiz indicada."""
    try:
        raiz_resuelta = raiz.expanduser().resolve()
    except OSError:
        return

    actual = path
    while actual != raiz_resuelta and _path_seguro_en_raiz(actual, raiz_resuelta):
        try:
            actual.rmdir()
        except OSError:
            return
        actual = actual.parent


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


def eliminar_torrent(torrent_hash: str, borrar_archivos: bool = False) -> bool:
    """
    Retira un torrent de qBittorrent.

    Por defecto no le pide a qBittorrent borrar archivos. Esto permite sacar el
    torrent del cliente antes de eliminar manualmente solo el MKV original tras
    generar la copia MP4 compatible.
    """
    if not torrent_hash:
        return False

    cliente = obtener_cliente(abrir_si_no_corre=False)
    if not cliente:
        return False

    try:
        resultado = cliente.torrents_delete(
            delete_files=borrar_archivos,
            torrent_hashes=[torrent_hash],
        )
        if resultado in (None, "Ok."):
            logger.info(f"Torrent retirado de qBittorrent: {torrent_hash[:12]}")
            return True
        logger.warning(f"qBittorrent respondio al retirar torrent: {resultado}")
        return False
    except Exception as e:
        logger.warning(f"No se pudo retirar torrent de qBittorrent {torrent_hash[:12]}: {e}")
        return False


def _candidatos_archivo_torrent(torrent: dict, ruta_relativa: str) -> list[Path]:
    """Devuelve posibles rutas absolutas para un archivo de un torrent."""
    candidatos = []
    save_path = torrent.get("ruta")
    content_path = torrent.get("content_path")
    nombre = torrent.get("nombre")

    if save_path:
        candidatos.append(Path(save_path) / ruta_relativa)
        if nombre:
            candidatos.append(Path(save_path) / nombre / ruta_relativa)
    if content_path:
        content = Path(content_path)
        candidatos.append(content / ruta_relativa)
        if content.name == Path(ruta_relativa).name:
            candidatos.append(content)

    return candidatos


def renombrar_archivo_torrent(path_actual: str, nombre_nuevo: str) -> str | None:
    """
    Renombra un archivo administrado por qBittorrent usando su API.

    Retorna la nueva ruta absoluta si encuentra el archivo y la API acepta el
    cambio. Si qBittorrent no esta disponible o el archivo no pertenece a un
    torrent conocido, retorna None para que el llamador decida el fallback.
    """
    if not path_actual or not nombre_nuevo:
        return None

    cliente = obtener_cliente(abrir_si_no_corre=False)
    if not cliente:
        return None

    try:
        objetivo = Path(path_actual).expanduser().resolve()
    except OSError:
        return None

    try:
        torrents = listar_torrents(
            incluir_todos=getattr(config, "QBIT_BUSCAR_TODAS_LAS_DESCARGAS", True),
            iniciar_si_no_corre=False,
        )
        for torrent in torrents:
            torrent_hash = torrent.get("hash")
            if not torrent_hash:
                continue

            try:
                archivos = cliente.torrents_files(torrent_hash=torrent_hash)
            except Exception:
                continue

            for archivo in archivos:
                ruta_relativa = _torrent_attr(archivo, "name", "")
                if not ruta_relativa:
                    continue

                for candidato in _candidatos_archivo_torrent(torrent, ruta_relativa):
                    try:
                        if candidato.expanduser().resolve() != objetivo:
                            continue
                    except OSError:
                        continue

                    nueva_relativa = nombre_nuevo
                    _renombrar_archivo_relativo(
                        cliente,
                        torrent_hash,
                        ruta_relativa,
                        nueva_relativa,
                    )
                    logger.info(
                        "Archivo renombrado por qBittorrent: "
                        f"{ruta_relativa} -> {nueva_relativa}"
                    )
                    save_path = torrent.get("ruta")
                    if save_path:
                        return str(Path(save_path) / nueva_relativa)
                    return str(objetivo.with_name(nombre_nuevo))
    except Exception as e:
        logger.debug(f"No se pudo renombrar via qBittorrent: {e}")

    return None


def normalizar_video_principal_torrent(
    torrent: dict,
    nombre_base_canonico: str,
    carpeta_destino: str | None = None,
) -> dict | None:
    """
    Mueve/renombra el video principal de un torrent a la raiz del destino.

    qBittorrent puede tener un nombre de torrent limpio, pero conservar dentro
    una carpeta release con spam. Esta funcion cambia la ruta interna del video
    principal de, por ejemplo, `Release/FIFA World Cup.mkv` a
    `004_estados_unidos_vs_paraguay_en.mkv`.
    """
    torrent_hash = torrent.get("hash")
    if not torrent_hash or not nombre_base_canonico:
        return None

    cliente = obtener_cliente(abrir_si_no_corre=False)
    if not cliente:
        return None

    try:
        archivos = cliente.torrents_files(torrent_hash=torrent_hash)
    except Exception as e:
        logger.debug(f"No se pudieron listar archivos del torrent {torrent_hash}: {e}")
        return None

    videos = [
        archivo for archivo in archivos
        if _extension_video(_torrent_attr(archivo, "name", ""))
    ]
    if not videos:
        return None

    video = max(videos, key=_tamano_archivo_torrent)
    ruta_relativa = _torrent_attr(video, "name", "")
    if not ruta_relativa:
        return None

    extension = Path(ruta_relativa).suffix.lower()
    nombre_nuevo = f"{nombre_base_canonico}{extension}"
    nueva_relativa = nombre_nuevo
    destino_base = carpeta_destino or torrent.get("ruta") or config.DIRECTORIO_BASE
    ruta_final = str(Path(destino_base) / nueva_relativa)

    info = {
        "nombre_canonico": nombre_nuevo,
        "archivo_local": ruta_final,
        "archivo_local_ultimo": ruta_final,
        "archivo_relativo_torrent": nueva_relativa,
    }

    if ruta_relativa == nueva_relativa:
        info.update({
            "renombrado": False,
            "metodo_renombrado": "qbittorrent",
        })
        return info

    try:
        _renombrar_archivo_relativo(
            cliente,
            torrent_hash,
            ruta_relativa,
            nueva_relativa,
        )
    except Exception as e:
        logger.warning(
            "No se pudo normalizar archivo interno de qBittorrent "
            f"{ruta_relativa} -> {nueva_relativa}: {e}"
        )
        return None

    logger.info(
        "Archivo de video normalizado por qBittorrent: "
        f"{ruta_relativa} -> {nueva_relativa}"
    )
    info.update({
        "renombrado": True,
        "renombrado_en": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "archivo_nombre_anterior": Path(ruta_relativa).name,
        "archivo_relativo_anterior": ruta_relativa,
        "metodo_renombrado": "qbittorrent_flatten",
    })
    return info


def limpiar_auxiliares_torrent(
    torrent: dict,
    carpeta_destino: str | None = None,
) -> dict:
    """
    Marca como no descargables y borra auxiliares pequenos de spam.

    Solo limpia extensiones declaradas en QBIT_EXTENSIONES_AUXILIARES. No toca
    subtitulos ni archivos desconocidos para no perder material util.
    """
    resumen = {"auxiliares_limpiados": 0, "auxiliares_omitidos": 0}
    if not getattr(config, "QBIT_LIMPIAR_AUXILIARES", True):
        return resumen

    torrent_hash = torrent.get("hash")
    if not torrent_hash:
        return resumen

    cliente = obtener_cliente(abrir_si_no_corre=False)
    if not cliente:
        return resumen

    try:
        archivos = cliente.torrents_files(torrent_hash=torrent_hash)
    except Exception as e:
        logger.debug(f"No se pudieron listar auxiliares del torrent {torrent_hash}: {e}")
        return resumen

    auxiliares = []
    for archivo in archivos:
        ruta_relativa = _torrent_attr(archivo, "name", "")
        if not ruta_relativa or _extension_video(ruta_relativa):
            continue
        if not _extension_auxiliar_limpiable(ruta_relativa):
            resumen["auxiliares_omitidos"] += 1
            continue
        auxiliares.append(archivo)

    if not auxiliares:
        return resumen

    ids = [
        _torrent_attr(archivo, "index", _torrent_attr(archivo, "id"))
        for archivo in auxiliares
    ]
    ids = [i for i in ids if i is not None]
    if ids:
        try:
            cliente.torrents_file_priority(
                torrent_hash=torrent_hash,
                file_ids=ids,
                priority=0,
            )
        except Exception as e:
            logger.debug(f"No se pudo bajar prioridad de auxiliares {torrent_hash}: {e}")

    raiz = Path(carpeta_destino or torrent.get("ruta") or config.DIRECTORIO_BASE)
    for archivo in auxiliares:
        ruta_relativa = _torrent_attr(archivo, "name", "")
        path = raiz / ruta_relativa
        if not _path_seguro_en_raiz(path, raiz):
            resumen["auxiliares_omitidos"] += 1
            continue
        try:
            if path.exists() and path.is_file():
                path.unlink()
                resumen["auxiliares_limpiados"] += 1
                logger.info(f"Auxiliar de torrent eliminado: {path.name}")
                _limpiar_directorios_vacios(path.parent, raiz)
        except OSError as e:
            resumen["auxiliares_omitidos"] += 1
            logger.debug(f"No se pudo eliminar auxiliar {path}: {e}")

    return resumen


def listar_descargas_mundial(iniciar_si_no_corre: bool = False) -> list:
    """Lista todas las descargas de la categoría Mundial2026."""
    return listar_torrents(incluir_todos=False, iniciar_si_no_corre=iniciar_si_no_corre)
