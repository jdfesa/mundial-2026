"""
Verificador local de archivos descargados.

Busca archivos de video en las carpetas configuradas, intenta asociarlos con
partidos del calendario y, si ffprobe esta disponible, extrae duracion,
resolucion e idioma de pistas de audio.
"""
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import config
from idioma_utils import detectar_idioma, idioma_es_final, normalizar_texto
from nombres_archivos import nombre_canonico_partido

logger = logging.getLogger("mundial")


def _directorios_busqueda(partido: dict | None = None) -> list[Path]:
    rutas = [Path(config.DIRECTORIO_BASE)]
    if partido and partido.get("ruta"):
        rutas.insert(0, Path(partido["ruta"]))
    for extra in getattr(config, "DIRECTORIOS_VERIFICACION_EXTRA", []):
        rutas.append(Path(extra).expanduser())

    unicas = []
    vistos = set()
    for ruta in rutas:
        try:
            resuelta = ruta.expanduser().resolve()
        except OSError:
            continue
        if resuelta in vistos or not resuelta.exists():
            continue
        vistos.add(resuelta)
        unicas.append(resuelta)
    return unicas


def _iter_videos(directorios: list[Path]) -> list[Path]:
    extensiones = tuple(e.lower() for e in getattr(config, "EXTENSIONES_VIDEO", []))
    videos = []
    for directorio in directorios:
        for path in directorio.rglob("*"):
            if path.is_file() and path.suffix.lower() in extensiones:
                videos.append(path)
    return videos


def _normalizar_match(texto: str | None) -> str:
    """Normaliza rutas/titulos para comparar snake_case, carpetas y nombres humanos."""
    texto = normalizar_texto(texto)
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def _score_candidato(partido: dict, path: Path) -> int:
    texto = _normalizar_match(str(path))
    score = 0

    archivo = _normalizar_match(partido.get("archivo"))
    if archivo and archivo in texto:
        score += 100

    equipo1 = _normalizar_match(partido.get("equipo1"))
    equipo2 = _normalizar_match(partido.get("equipo2"))
    if equipo1 and equipo1 in texto:
        score += 30
    if equipo2 and equipo2 in texto:
        score += 30

    partido_id = partido.get("id")
    if partido_id is not None and re.search(rf"\b0*{partido_id}\b", texto):
        score += 5

    return score


def _ffprobe(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"ffprobe": "no_disponible"}

    comando = [
        ffprobe,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=30)
    except Exception as e:
        return {"ffprobe": f"error: {e}"}

    if resultado.returncode != 0:
        return {"ffprobe": "error"}

    try:
        datos = json.loads(resultado.stdout)
    except json.JSONDecodeError:
        return {"ffprobe": "json_invalido"}

    return _extraer_metadata_ffprobe(datos)


def _extraer_metadata_ffprobe(datos: dict) -> dict:
    formato = datos.get("format", {})
    streams = datos.get("streams", [])
    meta = {"ffprobe": "ok"}

    try:
        duracion = float(formato.get("duration", 0))
        if duracion > 0:
            meta["duracion_min"] = round(duracion / 60, 1)
    except (TypeError, ValueError):
        pass

    try:
        bitrate = float(formato.get("bit_rate", 0))
        if bitrate > 0:
            meta["bitrate_kbps"] = round(bitrate / 1000)
    except (TypeError, ValueError):
        pass

    for stream in streams:
        if stream.get("codec_type") == "video" and "resolucion" not in meta:
            width = stream.get("width")
            height = stream.get("height")
            if width and height:
                meta["resolucion"] = f"{width}x{height}"
                meta["ancho"] = width
                meta["alto"] = height
            if stream.get("codec_name"):
                meta["codec_video"] = stream.get("codec_name")
            fps = _parse_fps(stream.get("r_frame_rate"))
            if fps:
                meta["fps"] = fps
        if stream.get("codec_type") == "audio":
            tags = stream.get("tags", {})
            idioma = tags.get("language")
            title = tags.get("title")
            texto = " ".join(str(v) for v in (idioma, title) if v)
            detectado = detectar_idioma(texto)
            if texto:
                meta.setdefault("pistas_audio", []).append(texto)
            if idioma_es_final(detectado):
                meta["idioma_audio"] = detectado

    return meta


def _parse_fps(valor: str | None) -> float | None:
    if not valor or valor == "0/0":
        return None
    try:
        if "/" in valor:
            numerador, denominador = valor.split("/", 1)
            denominador_float = float(denominador)
            if denominador_float == 0:
                return None
            return round(float(numerador) / denominador_float, 3)
        return round(float(valor), 3)
    except (TypeError, ValueError):
        return None


def _evaluar_postproceso(meta: dict) -> dict:
    umbral_gb = float(getattr(config, "POSTPROCESO_UMBRAL_GB", 5.0))
    altura_preferida = int(getattr(config, "ALTURA_PREFERIDA", 720))
    tamano_gb = round(float(meta.get("tamano_mb", 0)) / 1024, 2)
    alto = meta.get("alto")
    motivos = []

    if tamano_gb > umbral_gb:
        motivos.append(f"tamano>{umbral_gb:g}GB")
    if alto and alto > altura_preferida:
        motivos.append(f"resolucion>{altura_preferida}p")

    if motivos:
        estado = "revisar"
        accion = "evaluar_remux_o_compresion"
    else:
        estado = "omitido"
        accion = "mantener_origen"
        motivos.append("tamano_y_resolucion_ok")

    return {
        "estado": estado,
        "accion": accion,
        "motivo": ", ".join(motivos),
        "umbral_gb": umbral_gb,
        "altura_preferida": altura_preferida,
        "tamano_gb": tamano_gb,
    }


def _validar_archivo_ytdlp(meta: dict) -> tuple[bool, str | None]:
    duracion_min = meta.get("duracion_min")
    if not duracion_min:
        return False, "sin_duracion"
    if duracion_min and duracion_min * 60 > getattr(config, "YTDLP_DURACION_MAXIMA", 3 * 3600):
        return False, "duracion_larga"

    alto = meta.get("alto")
    if not alto:
        return False, "sin_altura"
    if alto and alto < getattr(config, "YTDLP_ALTURA_MINIMA", 720):
        return False, f"altura_baja:{alto}"

    return True, None


def _target_sin_colision(path: Path, nombre: str) -> Path:
    destino = path.with_name(nombre)
    if not destino.exists() or destino == path:
        return destino

    stem = destino.stem
    suffix = destino.suffix
    for indice in range(2, 100):
        candidato = destino.with_name(f"{stem}_{indice}{suffix}")
        if not candidato.exists():
            return candidato
    return destino.with_name(f"{stem}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}{suffix}")


def _proveedor_filesystem(partido: dict) -> bool:
    proveedores = getattr(config, "RENOMBRAR_PROVEEDORES_FILESYSTEM", {"manual", "yt-dlp"})
    return partido.get("proveedor") in proveedores


def _renombrar_si_corresponde(partido: dict, path: Path, idioma: str | None) -> tuple[Path, dict]:
    info = {
        "nombre_canonico": nombre_canonico_partido(partido, path.suffix, idioma),
        "renombrado": False,
    }
    if not getattr(config, "RENOMBRAR_ARCHIVOS_CANONICOS", True):
        return path, info

    nombre_canonico = info["nombre_canonico"]
    if path.name == nombre_canonico:
        return path, info

    try:
        from qbit_manager import renombrar_archivo_torrent

        nuevo_qbit = renombrar_archivo_torrent(str(path), nombre_canonico)
    except Exception as e:
        logger.debug(f"No se intento renombrado via qBittorrent: {e}")
        nuevo_qbit = None

    if nuevo_qbit:
        nuevo_path = Path(nuevo_qbit)
        info.update({
            "renombrado": True,
            "renombrado_en": datetime.now(timezone.utc).isoformat(),
            "archivo_nombre_anterior": path.name,
            "metodo_renombrado": "qbittorrent",
        })
        return nuevo_path, info

    if not _proveedor_filesystem(partido):
        info["renombrado_pendiente"] = True
        info["metodo_renombrado"] = "pendiente_qbittorrent"
        return path, info

    destino = _target_sin_colision(path, nombre_canonico)
    try:
        path.rename(destino)
    except OSError as e:
        logger.warning(f"No se pudo renombrar archivo local {path.name}: {e}")
        info["renombrado_error"] = str(e)
        return path, info

    logger.info(f"Archivo renombrado: {path.name} -> {destino.name}")
    info.update({
        "renombrado": True,
        "renombrado_en": datetime.now(timezone.utc).isoformat(),
        "archivo_nombre_anterior": path.name,
        "metodo_renombrado": "filesystem",
    })
    if destino.name != nombre_canonico:
        info["nombre_canonico"] = destino.name
        info["colision_nombre_canonico"] = nombre_canonico
    return destino, info


def verificar_partido(
    partido: dict,
    videos_cache: list[Path] | None = None,
    renombrar_archivos: bool = False,
) -> dict | None:
    """Busca el mejor archivo local para un partido y devuelve metadata."""
    directorios = _directorios_busqueda(partido)
    videos = videos_cache if videos_cache is not None else _iter_videos(directorios)
    candidatos = []

    for video in videos:
        try:
            if not any(video.is_relative_to(d) for d in directorios):
                continue
        except AttributeError:
            if not any(str(video).startswith(str(d)) for d in directorios):
                continue
        score = _score_candidato(partido, video)
        if score > 0:
            candidatos.append((score, video))

    if not candidatos:
        return None

    def _tamano_seguro(item: tuple[int, Path]) -> int:
        try:
            return item[1].stat().st_size
        except OSError:
            return 0

    candidatos.sort(key=lambda item: (item[0], _tamano_seguro(item)), reverse=True)
    _, path = candidatos[0]
    try:
        stat = path.stat()
    except OSError:
        return None
    meta = {
        "archivo_local": str(path),
        "archivo_local_ultimo": str(path),
        "archivo_existe": True,
        "archivo_local_estado": "presente",
        "tamano_mb": round(stat.st_size / (1024 * 1024), 1),
        "verificado_en": datetime.now(timezone.utc).isoformat(),
    }
    meta.update(_ffprobe(path))

    texto_idioma = " ".join(
        [
            path.name,
            " ".join(meta.get("pistas_audio", [])),
            meta.get("idioma_audio", ""),
        ]
    )
    idioma = meta.get("idioma_audio") or detectar_idioma(texto_idioma)
    meta["idioma_detectado_archivo"] = idioma

    if renombrar_archivos:
        path_renombrado, info_nombre = _renombrar_si_corresponde(partido, path, idioma)
        meta.update(info_nombre)
        if path_renombrado != path:
            path = path_renombrado
            meta["archivo_local"] = str(path)
            meta["archivo_local_ultimo"] = str(path)
            try:
                stat = path.stat()
                meta["tamano_mb"] = round(stat.st_size / (1024 * 1024), 1)
            except OSError:
                meta["archivo_existe"] = False
                meta["archivo_local_estado"] = "renombrado_pendiente_verificacion"
    else:
        meta["nombre_canonico"] = nombre_canonico_partido(partido, path.suffix, idioma)

    meta["postproceso"] = _evaluar_postproceso(meta)
    return meta


def _registrar_archivo_ausente(partido: dict) -> None:
    ultimo = partido.get("archivo_local") or partido.get("archivo_local_ultimo")
    if ultimo:
        partido["archivo_local_ultimo"] = ultimo
        partido["archivo_local_estado"] = "movido_o_borrado"
    else:
        partido["archivo_local_estado"] = "sin_archivo_local"
    partido["archivo_local"] = None
    partido["archivo_existe"] = False
    partido["verificado_en"] = datetime.now(timezone.utc).isoformat()


def verificar_archivos(calendario: list[dict], renombrar_archivos: bool = False) -> dict:
    """Actualiza los partidos con metadata local y retorna resumen."""
    videos_cache = _iter_videos(_directorios_busqueda())
    resumen = {"verificados": 0, "encontrados": 0, "sin_archivo": 0}

    for partido in calendario:
        if not partido.get("descargado"):
            continue
        resumen["verificados"] += 1
        meta = verificar_partido(partido, videos_cache, renombrar_archivos=renombrar_archivos)
        if not meta:
            _registrar_archivo_ausente(partido)
            resumen["sin_archivo"] += 1
            continue

        resumen["encontrados"] += 1
        partido.update(meta)

        if partido.get("proveedor") == "yt-dlp":
            valido, razon = _validar_archivo_ytdlp(meta)
            partido["archivo_valido"] = valido
            if not valido:
                partido["archivo_rechazado"] = partido.get("archivo_local")
                partido["validacion_error"] = razon
                partido["archivo_local_ultimo"] = partido.get("archivo_local")
                partido["archivo_local"] = None
                partido["archivo_local_estado"] = "rechazado"
                partido["archivo_existe"] = False
                partido["descargado"] = False
                partido["estado_final"] = False
                partido["necesita_mejora"] = False
                partido["descarga_estado"] = "rechazada"
                logger.warning(
                    "Archivo yt-dlp rechazado para "
                    f"{partido.get('equipo1')} vs {partido.get('equipo2')}: {razon}"
                )
                continue

        idioma_archivo = meta.get("idioma_detectado_archivo")
        if idioma_archivo and idioma_es_final(idioma_archivo):
            partido["idioma"] = idioma_archivo
            partido["estado_final"] = True
            partido["necesita_mejora"] = False

    logger.info(
        "Verificacion local: "
        f"{resumen['encontrados']}/{resumen['verificados']} archivos encontrados"
    )
    return resumen
