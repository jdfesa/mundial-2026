"""
Genera copias MP4 compatibles con navegador para la biblioteca HTML.

El objetivo no es comprimir ni cambiar la calidad del video: se copia el stream
de video y solo se convierte el audio cuando el codec no es compatible con
Chrome/HTML5, por ejemplo AC3 dentro de MKV.
"""
import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import config
from nombres_archivos import nombre_canonico_partido

logger = logging.getLogger("mundial")


def _ffprobe_path() -> str | None:
    return shutil.which("ffprobe")


def _ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def _metadata_media(path: Path) -> dict:
    ffprobe = _ffprobe_path()
    if not ffprobe:
        return {"ffprobe": "no_disponible"}

    comando = [
        ffprobe,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        str(path),
    ]
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=30)
    except Exception as e:
        return {"ffprobe": f"error: {e}"}

    if resultado.returncode != 0:
        return {"ffprobe": "error", "detalle": resultado.stderr.strip()}

    try:
        datos = json.loads(resultado.stdout)
    except json.JSONDecodeError:
        return {"ffprobe": "json_invalido"}

    meta = {"ffprobe": "ok", "audio_streams": 0, "video_streams": 0}
    for stream in datos.get("streams", []):
        tipo = stream.get("codec_type")
        if tipo == "video":
            meta["video_streams"] += 1
            if "codec_video" not in meta and stream.get("codec_name"):
                meta["codec_video"] = stream.get("codec_name")
            if "ancho" not in meta and stream.get("width"):
                meta["ancho"] = stream.get("width")
            if "alto" not in meta and stream.get("height"):
                meta["alto"] = stream.get("height")
        elif tipo == "audio":
            meta["audio_streams"] += 1
            codec = stream.get("codec_name")
            if codec:
                meta.setdefault("codecs_audio", []).append(codec)
            if "codec_audio" not in meta and codec:
                meta["codec_audio"] = codec
            if "canales_audio" not in meta and stream.get("channels"):
                meta["canales_audio"] = stream.get("channels")
            if "layout_audio" not in meta and stream.get("channel_layout"):
                meta["layout_audio"] = stream.get("channel_layout")
    return meta


def _audio_compatible(meta: dict) -> bool:
    codec = str(meta.get("codec_audio") or "").lower()
    return codec in getattr(config, "WEB_COMPAT_AUDIO_CODECS", {"aac", "mp3"})


def _video_copiable(meta: dict) -> bool:
    codec = str(meta.get("codec_video") or "").lower()
    return codec in getattr(config, "WEB_COMPAT_VIDEO_COPY_CODECS", {"h264"})


def _archivo_compatible_web(path: Path, meta: dict | None = None) -> bool:
    meta = meta or _metadata_media(path)
    return path.suffix.lower() == ".mp4" and _video_copiable(meta) and _audio_compatible(meta)


def _ruta_existente(*rutas: str | None) -> Path | None:
    for ruta in rutas:
        if not ruta:
            continue
        path = Path(ruta)
        if path.exists() and path.is_file():
            return path
    return None


def _destino_mp4(partido: dict, origen: Path) -> Path:
    nombre = nombre_canonico_partido(partido, ".mp4", partido.get("idioma"))
    destino = origen.with_name(nombre)
    try:
        if destino.resolve() == origen.resolve():
            return origen.with_name(f"{origen.stem}_web.mp4")
    except OSError:
        pass
    return destino


def _estado(
    estado: str,
    motivo: str,
    origen: Path | None = None,
    destino: Path | None = None,
    meta: dict | None = None,
) -> dict:
    datos = {
        "estado": estado,
        "motivo": motivo,
        "actualizado_en": datetime.now(timezone.utc).isoformat(),
    }
    if origen:
        datos["origen"] = str(origen)
    if destino:
        datos["archivo"] = str(destino)
    if meta:
        for campo in ("codec_video", "codec_audio", "canales_audio", "layout_audio"):
            if campo in meta:
                datos[campo] = meta[campo]
    return datos


def _marcar_compatible(partido: dict, path: Path, meta: dict, motivo: str) -> None:
    ahora = datetime.now(timezone.utc).isoformat()
    partido["archivo_web"] = str(path)
    partido["archivo_web_ultimo"] = str(path)
    partido["archivo_web_existe"] = True
    partido["archivo_local"] = str(path)
    partido["archivo_local_ultimo"] = str(path)
    partido["archivo_existe"] = True
    partido["nombre_canonico"] = path.name
    partido["archivo"] = path.name
    partido["codec_video"] = meta.get("codec_video")
    partido["codec_audio"] = meta.get("codec_audio")
    partido["codecs_audio"] = meta.get("codecs_audio")
    partido["canales_audio"] = meta.get("canales_audio")
    partido["layout_audio"] = meta.get("layout_audio")
    partido["audio_compatible_web"] = True
    partido["postprocesado_web_en"] = ahora
    partido["compatibilidad_web"] = _estado("compatible", motivo, destino=path, meta=meta)
    try:
        partido["tamano_mb"] = round(path.stat().st_size / (1024 * 1024), 1)
    except OSError:
        pass


def _marcar_no_compatible(
    partido: dict,
    estado: str,
    motivo: str,
    origen: Path | None = None,
    destino: Path | None = None,
    meta: dict | None = None,
) -> None:
    partido["audio_compatible_web"] = False
    partido["archivo_web_existe"] = False
    if partido.get("archivo_web"):
        partido["archivo_web_ultimo"] = partido.get("archivo_web")
    partido["compatibilidad_web"] = _estado(estado, motivo, origen, destino, meta)


def _espacio_suficiente(destino: Path, tamano_origen: int) -> tuple[bool, str | None]:
    try:
        libre = shutil.disk_usage(destino.parent).free
    except OSError as e:
        return False, f"no_se_pudo_medir_espacio:{e}"

    min_libre_gb = float(getattr(config, "WEB_COMPAT_MIN_FREE_GB", 1.0))
    minimo_libre = int(min_libre_gb * 1024**3)
    requerido = tamano_origen + minimo_libre
    if libre < requerido:
        libre_gb = round(libre / 1024**3, 2)
        requerido_gb = round(requerido / 1024**3, 2)
        return False, f"espacio_insuficiente:{libre_gb}GB_libres<{requerido_gb}GB_requeridos"
    return True, None


def _convertir(origen: Path, destino: Path) -> tuple[bool, str | None]:
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        return False, "ffmpeg_no_disponible"

    temp = destino.with_name(f".{destino.stem}.tmp{destino.suffix}")
    try:
        if temp.exists():
            temp.unlink()
    except OSError as e:
        return False, f"no_se_pudo_limpiar_tmp:{e}"

    comando = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(origen),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        getattr(config, "WEB_COMPAT_AUDIO_BITRATE", "192k"),
        "-ac",
        str(getattr(config, "WEB_COMPAT_AUDIO_CHANNELS", 2)),
        "-sn",
        "-movflags",
        "+faststart",
        str(temp),
    ]

    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=int(getattr(config, "WEB_COMPAT_TIMEOUT_SEGUNDOS", 7200)),
        )
    except subprocess.TimeoutExpired:
        return False, "ffmpeg_timeout"
    except Exception as e:
        return False, f"ffmpeg_error:{e}"

    if resultado.returncode != 0:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass
        detalle = (resultado.stderr or resultado.stdout or "").strip().splitlines()
        return False, "ffmpeg_fallo:" + (detalle[-1][:180] if detalle else "sin_detalle")

    try:
        temp.replace(destino)
    except OSError as e:
        return False, f"no_se_pudo_mover_tmp:{e}"
    return True, None


def _retirar_torrent_original(partido: dict) -> tuple[bool, str | None]:
    torrent_hash = partido.get("torrent_hash")
    if not torrent_hash:
        return True, None
    if not getattr(config, "WEB_COMPAT_RETIRAR_TORRENT_ORIGINAL", True):
        return False, "retiro_torrent_deshabilitado"

    try:
        from qbit_manager import eliminar_torrent
    except Exception as e:
        return False, f"qbit_manager_no_disponible:{e}"

    if eliminar_torrent(torrent_hash, borrar_archivos=False):
        partido["torrent_retirado_postproceso"] = True
        partido["torrent_retirado_postproceso_en"] = datetime.now(timezone.utc).isoformat()
        return True, None
    return False, "no_se_pudo_retirar_torrent"


def postprocesar_partido_web(partido: dict, dry_run: bool = False) -> str:
    """Postprocesa un partido y retorna el estado resumido."""
    if not partido.get("descargado"):
        return "omitido"

    existente_web = _ruta_existente(partido.get("archivo_web"), partido.get("archivo_web_ultimo"))
    if existente_web:
        meta_web = _metadata_media(existente_web)
        if _archivo_compatible_web(existente_web, meta_web):
            _marcar_compatible(partido, existente_web, meta_web, "mp4_existente")
            return "compatible"

    origen = _ruta_existente(partido.get("archivo_local"), partido.get("archivo_local_ultimo"))
    if not origen:
        _marcar_no_compatible(partido, "sin_archivo_local", "no_hay_archivo_para_postprocesar")
        return "sin_archivo"

    meta = _metadata_media(origen)
    if meta.get("ffprobe") != "ok":
        _marcar_no_compatible(partido, "omitido", str(meta.get("ffprobe")), origen, meta=meta)
        return "omitido"

    if _archivo_compatible_web(origen, meta):
        _marcar_compatible(partido, origen, meta, "origen_compatible")
        return "compatible"

    if not getattr(config, "WEB_COMPAT_POSTPROCESO", True):
        _marcar_no_compatible(partido, "deshabilitado", "WEB_COMPAT_POSTPROCESO=0", origen, meta=meta)
        return "omitido"

    if not _video_copiable(meta):
        _marcar_no_compatible(partido, "omitido", "video_requeriria_recodificacion", origen, meta=meta)
        return "omitido"

    if int(meta.get("audio_streams") or 0) < 1:
        _marcar_no_compatible(partido, "omitido", "sin_audio", origen, meta=meta)
        return "omitido"

    destino = _destino_mp4(partido, origen)
    if destino.exists():
        meta_destino = _metadata_media(destino)
        if _archivo_compatible_web(destino, meta_destino):
            _marcar_compatible(partido, destino, meta_destino, "mp4_existente")
            return "compatible"

    try:
        tamano_origen = origen.stat().st_size
    except OSError:
        _marcar_no_compatible(partido, "sin_archivo_local", "origen_no_lee_stat", origen, destino, meta)
        return "sin_archivo"

    ok_espacio, motivo_espacio = _espacio_suficiente(destino, tamano_origen)
    if not ok_espacio:
        _marcar_no_compatible(partido, "pendiente", motivo_espacio or "espacio_insuficiente", origen, destino, meta)
        return "pendiente"

    logger.info(
        "Postproceso web: "
        f"{origen.name} ({meta.get('codec_audio', 'audio?')}) -> {destino.name} (aac/mp4)"
    )
    if dry_run:
        _marcar_no_compatible(partido, "dry_run", "se_convertiria_a_mp4_aac", origen, destino, meta)
        return "pendiente"

    exito, error = _convertir(origen, destino)
    if not exito:
        _marcar_no_compatible(partido, "error", error or "ffmpeg_fallo", origen, destino, meta)
        logger.warning(f"No se pudo generar MP4 compatible para {origen.name}: {error}")
        return "error"

    meta_final = _metadata_media(destino)
    if not _archivo_compatible_web(destino, meta_final):
        _marcar_no_compatible(partido, "error", "mp4_generado_no_compatible", origen, destino, meta_final)
        return "error"

    _marcar_compatible(partido, destino, meta_final, "convertido_audio_aac")
    partido["archivo_origen_postproceso"] = str(origen)

    if not getattr(config, "WEB_COMPAT_CONSERVAR_ORIGINAL", True):
        retirado, motivo_retiro = _retirar_torrent_original(partido)
        if not retirado:
            partido["archivo_origen_eliminado_error"] = motivo_retiro
            partido["compatibilidad_web"] = _estado(
                "compatible_origen_conservado",
                motivo_retiro or "no_se_pudo_retirar_torrent",
                origen,
                destino,
                meta_final,
            )
            logger.warning(
                "MP4 generado, pero se conserva el MKV porque no se pudo retirar "
                f"el torrent de qBittorrent: {origen.name}"
            )
            return "convertido"

        try:
            if origen.exists() and origen.resolve() != destino.resolve():
                origen.unlink()
                partido["archivo_origen_eliminado"] = True
                partido["archivo_origen_eliminado_en"] = datetime.now(timezone.utc).isoformat()
        except OSError as e:
            partido["archivo_origen_eliminado_error"] = str(e)
            logger.warning(f"No se pudo eliminar origen tras postproceso: {origen.name}: {e}")

    return "convertido"


def postprocesar_compatibilidad_web(calendario: list[dict], dry_run: bool = False) -> dict:
    """Genera MP4 compatibles para los partidos descargados que lo requieran."""
    resumen = {
        "verificados": 0,
        "compatibles": 0,
        "convertidos": 0,
        "pendientes": 0,
        "errores": 0,
        "omitidos": 0,
        "sin_archivo": 0,
    }
    for partido in calendario:
        if not partido.get("descargado"):
            continue
        resumen["verificados"] += 1
        estado = postprocesar_partido_web(partido, dry_run=dry_run)
        if estado == "compatible":
            resumen["compatibles"] += 1
        elif estado == "convertido":
            resumen["convertidos"] += 1
        elif estado == "pendiente":
            resumen["pendientes"] += 1
        elif estado == "error":
            resumen["errores"] += 1
        elif estado == "sin_archivo":
            resumen["sin_archivo"] += 1
        else:
            resumen["omitidos"] += 1

    if resumen["verificados"]:
        logger.info(
            "Compatibilidad web: "
            f"{resumen['compatibles']} compatibles, "
            f"{resumen['convertidos']} convertidos, "
            f"{resumen['pendientes']} pendientes, "
            f"{resumen['errores']} errores"
        )
    return resumen
