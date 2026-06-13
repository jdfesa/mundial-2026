#!/usr/bin/env python3
"""
🏆 Descargador Automático de Partidos - Mundial FIFA 2026
=========================================================
Script principal que coordina la búsqueda y descarga de partidos.

Uso:
    python descargar_partidos.py              # Ejecución normal
    python descargar_partidos.py --dry-run    # Simular sin descargar
    python descargar_partidos.py --status     # Ver estado de descargas
    python descargar_partidos.py --forzar ID  # Forzar descarga de un partido por ID
    python descargar_partidos.py --postprocesar-web  # Preparar MP4/AAC para HTML
"""
import json
import os
import re
import sys
import logging
from datetime import datetime, timedelta, timezone

import config
from estado_descargas import (
    aplicar_estado,
    cargar_estado,
    guardar_estado,
    guardar_estado_txt,
    normalizar_calendario,
)
from idioma_utils import detectar_idioma, etiqueta_idioma, idioma_es_final
from nombres_archivos import nombre_base_canonico_partido
from indice_biblioteca import generar_indice
from notificador import (
    notificar_descarga_iniciada,
    notificar_no_encontrado,
    notificar_resumen,
    notificar_error,
)
from reporte_diario import generar_reporte_diario
from organizador_descargas import sincronizar_descargas_completadas
from postprocesador_web import postprocesar_compatibilidad_web
from verificador_archivos import verificar_archivos


# ─── Logging ─────────────────────────────────────────────────────────────────

def configurar_logging():
    """Configura logging a archivo y consola."""
    logger = logging.getLogger("mundial")
    logger.setLevel(logging.DEBUG)

    # Handler para archivo
    fh = logging.FileHandler(config.ARCHIVO_LOG, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Handler para consola
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    ))

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


logger = configurar_logging()


# ─── Calendario ──────────────────────────────────────────────────────────────

def cargar_calendario() -> list[dict]:
    """Carga el calendario de partidos."""
    try:
        with open(config.ARCHIVO_CALENDARIO, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"No se encontró el calendario: {config.ARCHIVO_CALENDARIO}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Error parseando el calendario: {e}")
        sys.exit(1)


def guardar_calendario(datos: list[dict]):
    """Guarda el calendario actualizado."""
    with open(config.ARCHIVO_CALENDARIO, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    logger.debug("Calendario guardado")


def preparar_compatibilidad_web(calendario: list[dict], dry_run: bool = False) -> dict:
    """
    Genera MP4 compatibles con navegador y refresca metadata cuando aplica.

    Se ejecuta despues de sincronizar y verificar archivos locales, porque necesita
    trabajar sobre el nombre canonico final.
    """
    resumen = postprocesar_compatibilidad_web(calendario, dry_run=dry_run)
    if not dry_run and (resumen.get("convertidos") or resumen.get("compatibles")):
        verificar_archivos(calendario, renombrar_archivos=False)
    return resumen


# ─── Directorios ─────────────────────────────────────────────────────────────

def crear_directorio_partido(partido: dict) -> str:
    """Crea y retorna el directorio de destino para un partido."""
    from organizador_descargas import directorio_partido

    ruta = directorio_partido(partido)
    os.makedirs(ruta, exist_ok=True)
    return ruta


# ─── Lógica Principal ────────────────────────────────────────────────────────

def _extraer_torrent_hash(magnet: str | None) -> str | None:
    match = re.search(r"btih:([a-fA-F0-9]+)", magnet or "")
    if not match:
        return None
    return match.group(1).lower()


def partido_listo_para_buscar(partido: dict) -> bool:
    """
    Verifica si un partido está listo para buscar (ya terminó + tiempo de espera).
    """
    es_mejorable = False
    if partido.get("descargado"):
        idioma_actual = partido.get("idioma") or detectar_idioma(partido.get("archivo"))
        if idioma_es_final(idioma_actual):
            return False
        if not getattr(config, "PERMITIR_UPGRADE_IDIOMA", True):
            return False
        es_mejorable = True

    # Partidos de eliminatorias sin equipos definidos
    if partido.get("equipo1") == "Por definir":
        return False

    try:
        fecha_partido = datetime.fromisoformat(
            partido["fecha_hora_utc"].replace("Z", "+00:00")
        )
    except (KeyError, ValueError):
        return False

    ahora = datetime.now(timezone.utc)
    # El partido debe haber empezado hace al menos HORAS_ESPERA horas
    tiempo_minimo = fecha_partido + timedelta(hours=config.HORAS_ESPERA_POST_PARTIDO)

    if ahora < tiempo_minimo:
        return False

    if es_mejorable:
        ultimo = partido.get("ultimo_intento_mejora")
        try:
            if ultimo:
                ultimo_dt = datetime.fromisoformat(ultimo.replace("Z", "+00:00"))
                espera = getattr(config, "MINUTOS_ENTRE_REINTENTOS_MEJORA", 180)
                if ahora < ultimo_dt + timedelta(minutes=espera):
                    return False
        except ValueError:
            pass
        return True

    # Verificar si no superó el máximo de intentos para partidos sin descarga.
    intentos = partido.get("intentos", 0)
    if intentos >= config.MAX_INTENTOS:
        return False

    # Verificar tiempo entre reintentos normales.
    ultimo = partido.get("ultimo_intento")
    if ultimo:
        try:
            ultimo_dt = datetime.fromisoformat(ultimo.replace("Z", "+00:00"))
            if ahora < ultimo_dt + timedelta(minutes=config.MINUTOS_ENTRE_REINTENTOS):
                return False
        except ValueError:
            pass

    return True


def registrar_descarga(partido: dict, resultado: dict, ruta: str | None = None) -> None:
    """Actualiza campos de estado despues de iniciar/completar una descarga."""
    titulo = resultado.get("titulo") or partido.get("archivo") or ""
    idioma = resultado.get("idioma") or detectar_idioma(titulo)
    ahora = datetime.now(timezone.utc).isoformat()

    partido["descargado"] = True
    partido.setdefault("descargado_en", ahora)
    partido["ultima_descarga_en"] = ahora
    partido.setdefault("descarga_iniciada_en", ahora)
    partido["revisar_descarga_despues_de"] = (
        datetime.now(timezone.utc)
        + timedelta(minutes=getattr(config, "DESCARGA_REVISAR_DESPUES_MINUTOS", 60))
    ).isoformat()
    partido.setdefault("descarga_estado", "iniciada")
    partido.setdefault("descarga_progreso", 0)
    partido["archivo"] = titulo
    partido["proveedor"] = resultado.get("fuente")
    partido["ruta"] = ruta or resultado.get("ruta")
    torrent_hash = resultado.get("torrent_hash") or _extraer_torrent_hash(resultado.get("magnet"))
    if torrent_hash:
        partido["torrent_hash"] = torrent_hash
    partido["idioma"] = idioma
    partido["estado_final"] = idioma_es_final(idioma)
    partido["necesita_mejora"] = not partido["estado_final"]
    partido["nombre_base_canonico"] = nombre_base_canonico_partido(partido, idioma)


def resultado_mejora_estado(partido: dict, resultado: dict) -> bool:
    """
    Decide si conviene descargar el resultado.

    Si el partido no esta descargado, cualquier resultado valido sirve.
    Si ya esta en idioma final, no se mejora.
    Si esta en ingles/desconocido, solo se descarga un resultado final.
    """
    if not partido.get("descargado"):
        return True

    idioma_actual = partido.get("idioma") or detectar_idioma(partido.get("archivo"))
    if idioma_es_final(idioma_actual):
        return False

    idioma_resultado = resultado.get("idioma") or detectar_idioma(resultado.get("titulo"))
    return idioma_es_final(idioma_resultado)


def partido_mejorable(partido: dict) -> bool:
    """Indica si el partido ya tiene descarga pero no en idioma final."""
    if not partido.get("descargado"):
        return False
    idioma_actual = partido.get("idioma") or detectar_idioma(partido.get("archivo"))
    return not idioma_es_final(idioma_actual)


def registrar_intento_mejora(partido: dict) -> None:
    """Registra una revision de mejora sin consumir intentos normales."""
    partido["intentos_mejora"] = partido.get("intentos_mejora", 0) + 1
    partido["ultimo_intento_mejora"] = datetime.now(timezone.utc).isoformat()


def ytdlp_listo_para_fallback(partido: dict) -> tuple[bool, datetime | None]:
    """Indica si ya paso la espera larga para permitir fallback con yt-dlp."""
    try:
        fecha_partido = datetime.fromisoformat(
            partido["fecha_hora_utc"].replace("Z", "+00:00")
        )
    except (KeyError, ValueError):
        return False, None

    espera_horas = getattr(config, "YTDLP_HORAS_ESPERA_POST_PARTIDO", 24)
    minimo = fecha_partido + timedelta(hours=espera_horas)
    return datetime.now(timezone.utc) >= minimo, minimo


def procesar_partido(partido: dict, dry_run: bool = False, solo_manuales: bool = False) -> bool | None:
    """
    Busca y descarga un partido.
    
    Returns:
        True si se inició la descarga exitosamente
        False si se intento y fallo
        None si se omitio sin contarlo como intento
    """
    equipo1 = partido["equipo1"]
    equipo2 = partido["equipo2"]
    nombre = nombre_base_canonico_partido(partido)
    prioridad = partido.get("prioridad", "normal")

    logger.info(f"{'='*60}")
    logger.info(f"Procesando: {equipo1} vs {equipo2} "
                f"({partido.get('grupo', '?')}) "
                f"[Prioridad: {prioridad}]")
    logger.info(f"  Intento #{partido.get('intentos', 0) + 1}")

    if dry_run:
        logger.info(f"  [DRY RUN] Se buscaría pero no se descarga")

    # Primero probar fuentes declaradas manualmente. Esto permite sumar URLs
    # autorizadas sin tocar las fuentes existentes.
    if config.FUENTES_HABILITADAS.get("manuales", True):
        from fuentes_manuales import buscar_fuente_manual, descargar_fuente_manual

        fuente_manual = buscar_fuente_manual(partido)
        if fuente_manual:
            directorio = crear_directorio_partido(partido)
            resultado_previo = {
                "titulo": fuente_manual.get("titulo") or fuente_manual.get("nombre") or "",
                "fuente": "manual",
                "idioma": fuente_manual.get("idioma") or detectar_idioma(
                    f"{fuente_manual.get('titulo', '')} {fuente_manual.get('nombre', '')}"
                ),
            }
            if not resultado_mejora_estado(partido, resultado_previo):
                logger.info(
                    "  Fuente manual encontrada, pero no mejora idioma actual "
                    f"({etiqueta_idioma(partido.get('idioma'))})"
                )
                if solo_manuales:
                    if not dry_run and partido_mejorable(partido):
                        registrar_intento_mejora(partido)
                    return None
            else:
                resultado_manual = descargar_fuente_manual(
                    fuente=fuente_manual,
                    partido=partido,
                    directorio_destino=directorio,
                    dry_run=dry_run,
                )
                if resultado_manual:
                    resultado_manual["idioma"] = resultado_previo["idioma"]
                    registrar_descarga(partido, resultado_manual, directorio)
                    if not dry_run:
                        notificar_descarga_iniciada(equipo1, equipo2)
                    logger.info("  Fuente manual procesada correctamente")
                    return True
                logger.warning("  La fuente manual fallo; se continua con el flujo existente")

        elif solo_manuales:
            logger.info("  Sin fuente manual para este partido; se omite por --solo-manuales")
            return None

    # Importar buscador aquí para evitar imports circulares
    from buscador_torrents import obtener_mejor_resultado, buscar_ytdlp

    # Buscar en sitios torrent
    resultado = obtener_mejor_resultado(equipo1, equipo2)

    if resultado:
        resultado["idioma"] = resultado.get("idioma") or detectar_idioma(resultado.get("titulo"))
        logger.info(f"  ✅ Encontrado: '{resultado['titulo']}'")
        logger.info(f"     Fuente: {resultado['fuente']} | "
                    f"Seeders: {resultado['seeders']} | "
                    f"Tamaño: {resultado['tamano_gb']}GB | "
                    f"Idioma: {etiqueta_idioma(resultado['idioma'])}")

        if not resultado_mejora_estado(partido, resultado):
            logger.info(
                "  Resultado encontrado, pero no mejora el idioma actual "
                f"({etiqueta_idioma(partido.get('idioma'))}). No se encola duplicado."
            )
            if not dry_run and partido_mejorable(partido):
                registrar_intento_mejora(partido)
            return None

        if dry_run:
            logger.info(f"  [DRY RUN] Se enviaría a qBittorrent")
            return True

        # Enviar a qBittorrent
        from qbit_manager import enviar_magnet
        directorio = crear_directorio_partido(partido)
        nombre = nombre_base_canonico_partido(partido, resultado.get("idioma"))

        exito = enviar_magnet(
            magnet_link=resultado["magnet"],
            carpeta_destino=directorio,
            nombre_partido=nombre
        )

        if exito:
            notificar_descarga_iniciada(equipo1, equipo2)
            registrar_descarga(partido, resultado, directorio)
            logger.info(f"  🎉 Descarga iniciada en qBittorrent")
            return True
        else:
            logger.error(f"  ❌ Error al enviar a qBittorrent")
            return False
    else:
        # Fallback: intentar con yt-dlp
        listo_ytdlp, habilitado_desde = ytdlp_listo_para_fallback(partido)
        if not listo_ytdlp:
            detalle = (
                habilitado_desde.strftime("%Y-%m-%d %H:%M UTC")
                if habilitado_desde else "fecha desconocida"
            )
            logger.info(
                "  No se encontraron torrents. Se omite yt-dlp por seguridad "
                f"hasta {detalle}"
            )
            return None

        logger.info(f"  No se encontraron torrents. Intentando fallback validado con yt-dlp...")
        directorio = crear_directorio_partido(partido)

        if dry_run:
            logger.info(f"  [DRY RUN] Se intentaría con yt-dlp validado")
            return None if partido_mejorable(partido) else False

        resultado_yt = buscar_ytdlp(equipo1, equipo2, directorio)
        if resultado_yt:
            resultado_yt["idioma"] = resultado_yt.get("idioma") or detectar_idioma(
                resultado_yt.get("titulo")
            )
            if not resultado_mejora_estado(partido, resultado_yt):
                logger.info(
                    "  yt-dlp encontro resultado, pero no mejora el idioma actual "
                    f"({etiqueta_idioma(partido.get('idioma'))})"
                )
                if not dry_run and partido_mejorable(partido):
                    registrar_intento_mejora(partido)
                return None

            logger.info(f"  ✅ Descargado vía yt-dlp: {resultado_yt['titulo']}")
            registrar_descarga(partido, resultado_yt, resultado_yt.get("ruta"))
            return True
        else:
            if partido_mejorable(partido):
                registrar_intento_mejora(partido)
                logger.info("  No apareció mejora en español; se intentará nuevamente más adelante")
                return None

            intentos = partido.get("intentos", 0) + 1
            logger.warning(
                f"  ⚠️ No se encontró {equipo1} vs {equipo2} "
                f"(intento {intentos}/{config.MAX_INTENTOS})"
            )
            notificar_no_encontrado(equipo1, equipo2, intentos)
            return False


def mostrar_estado():
    """Muestra el estado actual de todas las descargas."""
    calendario = cargar_calendario()
    estado = cargar_estado()
    aplicar_estado(calendario, estado)
    normalizar_calendario(calendario)
    sincronizar_descargas_completadas(calendario, iniciar_qbit_si_no_corre=False)
    verificar_archivos(calendario, renombrar_archivos=False)
    guardar_estado(calendario, estado)
    generar_reporte_diario(calendario)
    generar_indice(calendario)
    ahora = datetime.now(timezone.utc)

    descargados = [p for p in calendario if p.get("descargado")]
    finales = [p for p in descargados if p.get("estado_final")]
    mejorables = [p for p in descargados if not p.get("estado_final")]
    pendientes = [p for p in calendario
                  if not p.get("descargado") and p.get("equipo1") != "Por definir"]
    por_definir = [p for p in calendario if p.get("equipo1") == "Por definir"]

    print("\n" + "="*70)
    print("🏆 MUNDIAL 2026 - ESTADO DE DESCARGAS")
    print("="*70)

    print(f"\n📊 Resumen: {len(descargados)} descargados | "
          f"{len(finales)} finales | "
          f"{len(mejorables)} mejorables | "
          f"{len(pendientes)} pendientes | "
          f"{len(por_definir)} por definir")

    if descargados:
        print(f"\n✅ DESCARGADOS ({len(descargados)}):")
        for p in descargados:
            estado = "FINAL" if p.get("estado_final") else "MEJORABLE"
            local = "local" if p.get("archivo_existe") else "historial"
            nombre_archivo = p.get("nombre_canonico") or p.get("nombre_base_canonico") or p.get("archivo")
            print(
                f"   {p['equipo1']} vs {p['equipo2']} ({p.get('grupo', '?')}) "
                f"- {etiqueta_idioma(p.get('idioma'))} - {estado} - {local} "
                f"- {nombre_archivo or '-'}"
            )

    # Próximos partidos
    proximos = []
    for p in pendientes:
        try:
            fecha = datetime.fromisoformat(p["fecha_hora_utc"].replace("Z", "+00:00"))
            if fecha > ahora:
                proximos.append((fecha, p))
        except (KeyError, ValueError):
            pass

    proximos.sort(key=lambda x: x[0])

    if proximos[:5]:
        print(f"\n⏳ PRÓXIMOS PARTIDOS:")
        for fecha, p in proximos[:5]:
            delta = fecha - ahora
            horas = int(delta.total_seconds() / 3600)
            print(f"   {p['equipo1']} vs {p['equipo2']} - "
                  f"en {horas}h ({fecha.strftime('%d/%m %H:%M')} UTC) "
                  f"{'⭐' if p.get('prioridad') == 'alta' else ''}")

    # Partidos listos para buscar
    listos = [p for p in calendario if partido_listo_para_buscar(p)]
    if listos:
        print(f"\n🔍 LISTOS PARA BUSCAR ({len(listos)}):")
        for p in listos:
            tipo = "mejora" if partido_mejorable(p) else "normal"
            intentos = p.get("intentos_mejora", 0) if tipo == "mejora" else p.get("intentos", 0)
            print(f"   {p['equipo1']} vs {p['equipo2']} "
                  f"({p.get('grupo', '?')}) - "
                  f"tipo: {tipo} - intentos: {intentos} "
                  f"{'⭐' if p.get('prioridad') == 'alta' else ''}")

    # Estado de qBittorrent
    try:
        from qbit_manager import listar_descargas_mundial
        descargas = listar_descargas_mundial()
        if descargas:
            print(f"\n📥 DESCARGAS EN qBittorrent ({len(descargas)}):")
            for d in descargas:
                print(f"   {d['nombre'][:50]}... - "
                      f"{d['progreso']}% - {d['estado']} - "
                      f"{d['tamano_gb']}GB")
    except Exception:
        pass

    print("\n" + "="*70)


def main():
    """Función principal del descargador."""
    # Parsear argumentos
    dry_run = "--dry-run" in sys.argv
    mostrar = "--status" in sys.argv
    solo_manuales = "--solo-manuales" in sys.argv
    solo_postprocesar_web = "--postprocesar-web" in sys.argv
    forzar_id = None
    marcar_id = None
    marcar_idioma = "en"
    marcar_archivo = None
    marcar_ruta = None

    def valor_arg(nombre: str) -> str | None:
        if nombre not in sys.argv:
            return None
        idx = sys.argv.index(nombre)
        if idx + 1 >= len(sys.argv):
            return None
        return sys.argv[idx + 1]

    if "--forzar" in sys.argv:
        idx = sys.argv.index("--forzar")
        if idx + 1 < len(sys.argv):
            try:
                forzar_id = int(sys.argv[idx + 1])
            except ValueError:
                logger.error("El ID debe ser un número entero")
                sys.exit(1)

    if "--marcar-descargado" in sys.argv:
        valor = valor_arg("--marcar-descargado")
        try:
            marcar_id = int(valor) if valor else None
        except ValueError:
            logger.error("El ID de --marcar-descargado debe ser un número entero")
            sys.exit(1)
        marcar_idioma = valor_arg("--idioma") or marcar_idioma
        marcar_archivo = valor_arg("--archivo")
        marcar_ruta = valor_arg("--ruta")

    if marcar_id:
        calendario = cargar_calendario()
        estado = cargar_estado()
        aplicar_estado(calendario, estado)
        normalizar_calendario(calendario)

        partido = next((p for p in calendario if p.get("id") == marcar_id), None)
        if not partido:
            logger.error(f"No se encontró partido con ID {marcar_id}")
            sys.exit(1)

        titulo = marcar_archivo or partido.get("archivo") or (
            f"{partido.get('equipo1')}_vs_{partido.get('equipo2')}"
        )
        registrar_descarga(
            partido,
            {"titulo": titulo, "fuente": "manual_estado", "idioma": marcar_idioma},
            marcar_ruta or partido.get("ruta"),
        )
        verificar_archivos(calendario, renombrar_archivos=False)
        if not dry_run:
            preparar_compatibilidad_web(calendario)
        guardar_estado(calendario, estado)
        generar_reporte_diario(calendario)
        generar_indice(calendario)
        logger.info(
            f"Partido {marcar_id} marcado como descargado "
            f"({etiqueta_idioma(marcar_idioma)})"
        )
        return

    if solo_postprocesar_web:
        calendario = cargar_calendario()
        estado = cargar_estado()
        aplicar_estado(calendario, estado)
        normalizar_calendario(calendario)
        if not dry_run:
            sincronizar_descargas_completadas(calendario, iniciar_qbit_si_no_corre=True)
            verificar_archivos(calendario, renombrar_archivos=True)
        else:
            verificar_archivos(calendario, renombrar_archivos=False)
        preparar_compatibilidad_web(calendario, dry_run=dry_run)
        if not dry_run:
            guardar_estado(calendario, estado)
            generar_reporte_diario(calendario)
            generar_indice(calendario)
        logger.info("Postproceso web finalizado")
        return

    if mostrar:
        mostrar_estado()
        return

    logger.info("="*60)
    logger.info("🏆 Descargador de Partidos - Mundial 2026")
    logger.info(f"   Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"   Modo: {'DRY RUN' if dry_run else 'PRODUCCIÓN'}")
    if solo_manuales:
        logger.info("   Fuentes: solo manuales")
    logger.info("="*60)

    # Cargar calendario
    calendario = cargar_calendario()
    estado = cargar_estado()
    aplicar_estado(calendario, estado)
    normalizar_calendario(calendario)
    if not dry_run:
        sincronizar_descargas_completadas(calendario, iniciar_qbit_si_no_corre=True)
        verificar_archivos(calendario, renombrar_archivos=True)
    logger.info(f"Calendario cargado: {len(calendario)} partidos")

    # Crear directorio base
    os.makedirs(config.DIRECTORIO_BASE, exist_ok=True)

    contadores = {"descargados": 0, "fallidos": 0, "pendientes": 0}

    if forzar_id:
        # Forzar descarga de un partido específico
        partido = next((p for p in calendario if p.get("id") == forzar_id), None)
        if not partido:
            logger.error(f"No se encontró partido con ID {forzar_id}")
            sys.exit(1)

        logger.info(f"Forzando descarga de: {partido['equipo1']} vs {partido['equipo2']}")
        partido["intentos"] = 0
        partido["descargado"] = False

        exito = procesar_partido(partido, dry_run=dry_run, solo_manuales=solo_manuales)
        if exito is True:
            contadores["descargados"] += 1
        elif exito is False:
            partido["intentos"] = partido.get("intentos", 0) + 1
            partido["ultimo_intento"] = datetime.now(timezone.utc).isoformat()
            contadores["fallidos"] += 1
        else:
            contadores["pendientes"] += 1

    else:
        # Procesar partidos pendientes
        # Priorizar: alta primero, luego por fecha
        partidos_a_buscar = [p for p in calendario if partido_listo_para_buscar(p)]

        if not partidos_a_buscar:
            logger.info("No hay partidos pendientes para buscar en este momento")
            # Mostrar próximo partido
            ahora = datetime.now(timezone.utc)
            proximos = []
            for p in calendario:
                if p.get("descargado") or p.get("equipo1") == "Por definir":
                    continue
                try:
                    fecha = datetime.fromisoformat(
                        p["fecha_hora_utc"].replace("Z", "+00:00")
                    )
                    if fecha > ahora:
                        proximos.append((fecha, p))
                except (KeyError, ValueError):
                    pass

            if proximos:
                proximos.sort(key=lambda x: x[0])
                prox_fecha, prox = proximos[0]
                delta = prox_fecha - ahora
                horas = int(delta.total_seconds() / 3600)
                logger.info(
                    f"Próximo partido: {prox['equipo1']} vs {prox['equipo2']} "
                    f"en {horas} horas "
                    f"({prox_fecha.strftime('%d/%m %H:%M')} UTC)"
                )
        else:
            # Ordenar: prioridad alta primero, luego por fecha
            partidos_a_buscar.sort(
                key=lambda p: (
                    0 if p.get("prioridad") == "alta" else 1,
                    p.get("fecha_hora_utc", ""),
                )
            )

            logger.info(f"Partidos a buscar: {len(partidos_a_buscar)}")

            for partido in partidos_a_buscar:
                exito = procesar_partido(
                    partido,
                    dry_run=dry_run,
                    solo_manuales=solo_manuales,
                )

                if exito is True:
                    contadores["descargados"] += 1
                elif exito is False:
                    partido["intentos"] = partido.get("intentos", 0) + 1
                    partido["ultimo_intento"] = datetime.now(timezone.utc).isoformat()
                    contadores["fallidos"] += 1
                else:
                    contadores["pendientes"] += 1

    # Guardar estado operativo separado del calendario.
    if not dry_run:
        sincronizar_descargas_completadas(calendario, iniciar_qbit_si_no_corre=True)
        verificar_archivos(calendario, renombrar_archivos=True)
        preparar_compatibilidad_web(calendario)
        guardar_estado(calendario, estado)
        generar_reporte_diario(calendario)
        generar_indice(calendario)
    else:
        guardar_estado_txt(calendario)
        generar_reporte_diario(calendario)

    # Resumen
    total_desc = sum(1 for p in calendario if p.get("descargado"))
    total_pend = sum(1 for p in calendario
                     if not p.get("descargado") and p.get("equipo1") != "Por definir")

    logger.info("")
    logger.info("="*60)
    logger.info(f"📊 RESUMEN DE EJECUCIÓN")
    logger.info(f"   Nuevas descargas: {contadores['descargados']}")
    logger.info(f"   Fallidos: {contadores['fallidos']}")
    logger.info(f"   Total descargados: {total_desc}/{len(calendario)}")
    logger.info(f"   Total pendientes: {total_pend}")
    logger.info("="*60)

    # Notificación resumen
    if contadores["descargados"] > 0 or contadores["fallidos"] > 0:
        notificar_resumen(
            contadores["descargados"],
            contadores["fallidos"],
            total_pend
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nInterrumpido por el usuario")
    except Exception as e:
        logger.error(f"Error fatal: {e}", exc_info=True)
        notificar_error(str(e)[:100])
        sys.exit(1)
