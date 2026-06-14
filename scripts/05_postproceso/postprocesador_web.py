"""
Genera copias MP4 compatibles con navegador para la biblioteca HTML.

El flujo normal copia el video cuando ya es razonable y solo convierte audio a
AAC. Si el origen es pesado o supera la altura preferida, transcodifica a un
MP4 H.264/AAC 720p/30fps para no conservar archivos enormes en la biblioteca.
"""
import json
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import config
from estado_partido import descarga_en_progreso
from idioma_utils import normalizar_texto
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


def _tamano_total(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        try:
            total += path.stat().st_size
        except OSError:
            pass
    return total


def _target_height() -> int:
    return int(getattr(config, "WEB_COMPAT_TARGET_HEIGHT", getattr(config, "ALTURA_PREFERIDA", 720)))


def _target_fps() -> int:
    return int(getattr(config, "WEB_COMPAT_TARGET_FPS", 30))


def _umbral_transcodificacion_bytes() -> int:
    umbral_gb = float(
        getattr(
            config,
            "WEB_COMPAT_TRANSCODE_UMBRAL_GB",
            getattr(config, "POSTPROCESO_UMBRAL_GB", 5.0),
        )
    )
    return int(umbral_gb * 1024**3)


def _requiere_transcodificacion_pesada(origenes: list[Path], meta: dict) -> bool:
    if not getattr(config, "WEB_COMPAT_TRANSCODE_PESADO", True):
        return False
    if _tamano_total(origenes) > _umbral_transcodificacion_bytes():
        return True
    try:
        return int(meta.get("alto") or 0) > _target_height()
    except (TypeError, ValueError):
        return False


def _ruta_existente(*rutas: str | None) -> Path | None:
    for ruta in rutas:
        if not ruta:
            continue
        path = Path(ruta)
        if path.exists() and path.is_file():
            return path
    return None


def _variantes_equipo(nombre: str | None) -> set[str]:
    variantes = {normalizar_texto(nombre)}
    try:
        from busqueda_reglas import traducir_equipo

        variantes.add(normalizar_texto(traducir_equipo(nombre or "")))
    except Exception:
        pass
    return {v for v in variantes if v}


def _score_path_partido(partido: dict, path: Path) -> int:
    texto = normalizar_texto(str(path))
    score = 0
    if any(variante in texto for variante in _variantes_equipo(partido.get("equipo1"))):
        score += 1
    if any(variante in texto for variante in _variantes_equipo(partido.get("equipo2"))):
        score += 1
    return score


def _orden_parte(path: Path) -> tuple[int, str]:
    match = re.search(r"(?:part|pt|cd|disc)\s*0*(\d+)", path.stem.lower())
    if match:
        return int(match.group(1)), path.name.lower()
    return 0, path.name.lower()


def _origenes_filesystem(partido: dict, origen: Path) -> list[Path]:
    base = Path(partido.get("ruta") or origen.parent)
    if not base.exists():
        return []
    extensiones = tuple(ext.lower() for ext in getattr(config, "EXTENSIONES_VIDEO", []))
    candidatos = []
    for path in base.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensiones:
            continue
        if path.suffix.lower() != origen.suffix.lower():
            continue
        try:
            if path.resolve() == origen.resolve() or _score_path_partido(partido, path) >= 2:
                candidatos.append(path)
        except OSError:
            continue
    candidatos = _unificar_paths(candidatos)
    if len(candidatos) <= 1:
        return []
    return sorted(candidatos, key=_orden_parte)


def _origenes_postproceso(partido: dict, origen: Path) -> list[Path]:
    """
    Devuelve los videos que componen el origen.

    Si qBittorrent sigue teniendo el torrent, se usan sus archivos para cubrir
    casos Part1/Part2. Si no, se procesa solamente la ruta conocida.
    """
    torrent_hash = partido.get("torrent_hash")
    if torrent_hash:
        try:
            from qbit_manager import rutas_videos_torrent

            rutas = rutas_videos_torrent(torrent_hash, partido.get("ruta"))
        except Exception as e:
            logger.debug(f"No se pudieron obtener partes del torrent: {e}")
            rutas = []
        origenes = [Path(ruta) for ruta in rutas if Path(ruta).exists()]
        if origenes:
            return origenes
    origenes_fs = _origenes_filesystem(partido, origen)
    if origenes_fs:
        return origenes_fs
    return [origen]


def _unificar_paths(paths: list[Path]) -> list[Path]:
    unicos = []
    vistos = set()
    for path in paths:
        try:
            key = str(path.expanduser().resolve())
        except OSError:
            key = str(path)
        if key in vistos:
            continue
        vistos.add(key)
        unicos.append(path)
    return unicos


def _destino_mp4(partido: dict, origen: Path) -> Path:
    nombre = nombre_canonico_partido(partido, ".mp4", partido.get("idioma"))
    destino = origen.with_name(nombre)
    try:
        if destino.resolve() == origen.resolve():
            return origen.with_name(f"{origen.stem}_web.mp4")
    except OSError:
        pass
    return destino


def _escape_concat_path(path: Path) -> str:
    return str(path).replace("'", "'\\''")


def _crear_archivo_concat(origenes: list[Path], destino: Path) -> Path | None:
    if len(origenes) <= 1:
        return None
    lista = destino.with_name(f".{destino.stem}.concat.txt")
    with open(lista, "w", encoding="utf-8") as f:
        for origen in origenes:
            f.write(f"file '{_escape_concat_path(origen)}'\n")
    return lista


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


def _filtro_video(meta: dict) -> str:
    alto = meta.get("alto")
    ancho = meta.get("ancho")
    target_h = _target_height()
    try:
        alto_int = int(alto)
        ancho_int = int(ancho)
    except (TypeError, ValueError):
        return f"scale=-2:{target_h},fps={_target_fps()}"

    salida_h = min(target_h, alto_int)
    salida_w = max(2, round((ancho_int * salida_h / alto_int) / 2) * 2)
    return f"scale={salida_w}:{salida_h},fps={_target_fps()}"


def _convertir(
    origenes: list[Path],
    destino: Path,
    meta: dict,
    transcodificar_video: bool = False,
) -> tuple[bool, str | None]:
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        return False, "ffmpeg_no_disponible"

    temp = destino.with_name(f".{destino.stem}.tmp{destino.suffix}")
    try:
        if temp.exists():
            temp.unlink()
    except OSError as e:
        return False, f"no_se_pudo_limpiar_tmp:{e}"

    concat_file = None
    try:
        concat_file = _crear_archivo_concat(origenes, destino)
    except OSError as e:
        return False, f"no_se_pudo_crear_concat:{e}"

    if concat_file:
        entrada = ["-f", "concat", "-safe", "0", "-i", str(concat_file)]
    else:
        entrada = ["-i", str(origenes[0])]

    comando = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        *entrada,
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
    ]
    if transcodificar_video:
        comando.extend([
            "-vf",
            _filtro_video(meta),
            "-c:v",
            "libx264",
            "-preset",
            getattr(config, "WEB_COMPAT_VIDEO_PRESET", "veryfast"),
            "-crf",
            str(getattr(config, "WEB_COMPAT_VIDEO_CRF", 23)),
            "-pix_fmt",
            "yuv420p",
        ])
    else:
        comando.extend(["-c:v", "copy"])

    comando.extend([
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
    ])

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
    finally:
        if concat_file:
            try:
                concat_file.unlink()
            except OSError:
                pass

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
        partido["torrent_retiro_omitido_por_config"] = True
        return False, "retiro_torrent_deshabilitado"

    try:
        from qbit_manager import eliminar_torrent
    except Exception as e:
        return False, f"qbit_manager_no_disponible:{e}"

    if eliminar_torrent(torrent_hash, borrar_archivos=False):
        partido["torrent_retirado_postproceso"] = True
        partido["torrent_retirado_postproceso_en"] = datetime.now(timezone.utc).isoformat()
        return True, None
    partido["torrent_retiro_error"] = "no_se_pudo_retirar_torrent"
    return False, "no_se_pudo_retirar_torrent"


def _path_en_raiz(path: Path, raiz: Path) -> bool:
    try:
        return path.expanduser().resolve().is_relative_to(raiz.expanduser().resolve())
    except AttributeError:
        try:
            return str(path.expanduser().resolve()).startswith(str(raiz.expanduser().resolve()))
        except OSError:
            return False
    except OSError:
        return False


def _limpiar_carpetas_vacias(path: Path, raiz: Path) -> None:
    try:
        actual = path.expanduser().resolve()
        raiz_resuelta = raiz.expanduser().resolve()
    except OSError:
        return
    while actual != raiz_resuelta and _path_en_raiz(actual, raiz_resuelta):
        try:
            actual.rmdir()
        except OSError:
            return
        actual = actual.parent


def _eliminar_origenes(partido: dict, origenes: list[Path], destino: Path) -> None:
    eliminados = []
    errores = []
    raiz = Path(config.DIRECTORIO_BASE)
    for origen in origenes:
        try:
            if not origen.exists() or origen.resolve() == destino.resolve():
                continue
            if not _path_en_raiz(origen, raiz):
                errores.append(f"fuera_de_directorio_base:{origen}")
                continue
            origen.unlink()
            eliminados.append(str(origen))
            _limpiar_carpetas_vacias(origen.parent, raiz)
        except OSError as e:
            errores.append(f"{origen}:{e}")

    if eliminados:
        partido["archivo_origen_eliminado"] = True
        partido["archivo_origen_eliminado_en"] = datetime.now(timezone.utc).isoformat()
        partido["archivos_origen_eliminados"] = eliminados
    if errores:
        partido["archivo_origen_eliminado_error"] = " | ".join(errores)
        logger.warning(f"No se pudieron eliminar todos los origenes: {partido['archivo_origen_eliminado_error']}")


def _marcar_historico_sin_archivo(partido: dict) -> None:
    ultimo = partido.get("archivo_local") or partido.get("archivo_local_ultimo")
    if ultimo:
        partido["archivo_local_ultimo"] = ultimo
    if partido.get("archivo_web"):
        partido["archivo_web_ultimo"] = partido.get("archivo_web")
    partido["archivo_local"] = None
    partido["archivo_existe"] = False
    partido["archivo_web_existe"] = False
    partido["archivo_local_estado"] = "movido_o_borrado"
    partido["compatibilidad_web"] = _estado("historico", "archivo_movido_o_borrado")


def postprocesar_partido_web(partido: dict, dry_run: bool = False) -> str:
    """Postprocesa un partido y retorna el estado resumido."""
    if not partido.get("descargado"):
        return "omitido"

    if descarga_en_progreso(partido):
        partido["compatibilidad_web"] = _estado("pendiente", "descarga_en_progreso")
        return "pendiente"

    existente_web = _ruta_existente(partido.get("archivo_web"), partido.get("archivo_web_ultimo"))
    meta_web = None
    if existente_web:
        meta_web = _metadata_media(existente_web)
        if (
            _archivo_compatible_web(existente_web, meta_web)
            and not _requiere_transcodificacion_pesada([existente_web], meta_web)
        ):
            _marcar_compatible(partido, existente_web, meta_web, "mp4_existente")
            return "compatible"

    origen = None
    if existente_web and meta_web and _archivo_compatible_web(existente_web, meta_web):
        origen = existente_web
    if not origen:
        origen = _ruta_existente(partido.get("archivo_local"), partido.get("archivo_local_ultimo"))
    if not origen:
        if partido.get("postprocesado_web_en") or partido.get("archivo_web_ultimo"):
            _marcar_historico_sin_archivo(partido)
            return "historico"
        _marcar_no_compatible(partido, "sin_archivo_local", "no_hay_archivo_para_postprocesar")
        return "sin_archivo"

    origenes = _origenes_postproceso(partido, origen)
    if str(origen.expanduser().resolve()) not in {
        str(path.expanduser().resolve()) for path in origenes
    }:
        origenes.insert(0, origen)
    origenes = _unificar_paths(origenes)

    meta = _metadata_media(origenes[0])
    if meta.get("ffprobe") != "ok":
        _marcar_no_compatible(partido, "omitido", str(meta.get("ffprobe")), origenes[0], meta=meta)
        return "omitido"

    transcodificar_video = _requiere_transcodificacion_pesada(origenes, meta)

    if len(origenes) == 1 and _archivo_compatible_web(origen, meta) and not transcodificar_video:
        _marcar_compatible(partido, origen, meta, "origen_compatible")
        return "compatible"

    if not getattr(config, "WEB_COMPAT_POSTPROCESO", True):
        _marcar_no_compatible(partido, "deshabilitado", "WEB_COMPAT_POSTPROCESO=0", origen, meta=meta)
        return "omitido"

    if not transcodificar_video and not _video_copiable(meta):
        _marcar_no_compatible(partido, "omitido", "video_requeriria_recodificacion", origen, meta=meta)
        return "omitido"

    if int(meta.get("audio_streams") or 0) < 1:
        _marcar_no_compatible(partido, "omitido", "sin_audio", origen, meta=meta)
        return "omitido"

    destino = _destino_mp4(partido, origen)
    if destino.exists():
        meta_destino = _metadata_media(destino)
        if (
            _archivo_compatible_web(destino, meta_destino)
            and not _requiere_transcodificacion_pesada([destino], meta_destino)
        ):
            _marcar_compatible(partido, destino, meta_destino, "mp4_existente")
            return "compatible"

    tamano_origen = _tamano_total(origenes)
    if tamano_origen <= 0:
        _marcar_no_compatible(partido, "sin_archivo_local", "origen_no_lee_stat", origenes[0], destino, meta)
        return "sin_archivo"

    ok_espacio, motivo_espacio = _espacio_suficiente(destino, tamano_origen)
    if not ok_espacio:
        _marcar_no_compatible(partido, "pendiente", motivo_espacio or "espacio_insuficiente", origen, destino, meta)
        return "pendiente"

    modo = "transcode_720p" if transcodificar_video else "remux_aac"
    partes = f"{len(origenes)} partes, " if len(origenes) > 1 else ""
    tamano_gb = round(tamano_origen / 1024**3, 2)
    logger.info(
        "Postproceso web: "
        f"{origen.name} ({partes}{tamano_gb}GB) -> {destino.name} ({modo})"
    )
    if dry_run:
        motivo = "se_transcodificaria_720p_aac" if transcodificar_video else "se_convertiria_a_mp4_aac"
        _marcar_no_compatible(partido, "dry_run", motivo, origen, destino, meta)
        return "pendiente"

    exito, error = _convertir(origenes, destino, meta, transcodificar_video)
    if not exito:
        _marcar_no_compatible(partido, "error", error or "ffmpeg_fallo", origen, destino, meta)
        logger.warning(f"No se pudo generar MP4 compatible para {origen.name}: {error}")
        return "error"

    meta_final = _metadata_media(destino)
    if not _archivo_compatible_web(destino, meta_final):
        _marcar_no_compatible(partido, "error", "mp4_generado_no_compatible", origen, destino, meta_final)
        return "error"

    motivo_final = "transcodificado_720p_30fps" if transcodificar_video else "convertido_audio_aac"
    _marcar_compatible(partido, destino, meta_final, motivo_final)
    partido["archivo_origen_postproceso"] = str(origenes[0])
    partido["archivos_origen_postproceso"] = [str(path) for path in origenes]
    partido["postproceso_modo"] = modo

    conservar_original = getattr(config, "WEB_COMPAT_CONSERVAR_ORIGINAL", True)
    if transcodificar_video:
        conservar_original = getattr(config, "WEB_COMPAT_CONSERVAR_ORIGINAL_PESADO", False)

    if not conservar_original:
        retirado, motivo_retiro = _retirar_torrent_original(partido)
        if not retirado:
            if getattr(config, "WEB_COMPAT_ELIMINAR_ORIGINAL_SIN_QBIT", False):
                partido["archivo_origen_eliminado_advertencia"] = motivo_retiro
                logger.warning(
                    "No se pudo retirar el torrent de qBittorrent, pero se eliminaran "
                    "origenes pesados porque WEB_COMPAT_ELIMINAR_ORIGINAL_SIN_QBIT=1"
                )
                _eliminar_origenes(partido, origenes, destino)
                return "convertido"
            partido["archivo_origen_eliminado_error"] = motivo_retiro
            partido["compatibilidad_web"] = _estado(
                "compatible_origen_conservado",
                motivo_retiro or "no_se_pudo_retirar_torrent",
                origenes[0],
                destino,
                meta_final,
            )
            logger.warning(
                "MP4 generado, pero se conserva el origen porque no se pudo retirar "
                f"el torrent de qBittorrent: {origenes[0].name}"
            )
            return "convertido"

        _eliminar_origenes(partido, origenes, destino)

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
        "historicos": 0,
        "purgados_idioma": 0,
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
        elif estado == "historico":
            resumen["historicos"] += 1
        else:
            resumen["omitidos"] += 1

        if estado in {"compatible", "convertido"}:
            try:
                from limpieza_idiomas import purgar_ingles_si_es_final

                purga = purgar_ingles_si_es_final(partido, dry_run=dry_run)
                resumen["purgados_idioma"] += purga.get("purgados", 0)
            except Exception as e:
                logger.debug(f"No se pudo ejecutar purga de idioma anterior: {e}")

    if resumen["verificados"]:
        logger.info(
            "Compatibilidad web: "
            f"{resumen['compatibles']} compatibles, "
            f"{resumen['convertidos']} convertidos, "
            f"{resumen['pendientes']} pendientes, "
            f"{resumen['errores']} errores, "
            f"{resumen['historicos']} historicos, "
            f"{resumen['purgados_idioma']} purgados por idioma"
        )
    return resumen
