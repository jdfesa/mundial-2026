"""
Asistente opcional via Groq.

Se usa como capa de ayuda: genera queries y clasifica resultados ya encontrados.
No reemplaza las fuentes configuradas ni descarga nada por su cuenta.
"""
import json
import logging
import re
from functools import lru_cache

import requests

import config

logger = logging.getLogger("mundial")


def habilitado() -> bool:
    return bool(getattr(config, "GROQ_HABILITADO", False))


def _json_desde_texto(texto: str) -> dict | None:
    texto = (texto or "").strip()
    if not texto:
        return None

    if texto.startswith("```"):
        texto = re.sub(r"^```(?:json)?", "", texto, flags=re.IGNORECASE).strip()
        texto = re.sub(r"```$", "", texto).strip()

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", texto, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _chat_json(system: str, user: str) -> dict | None:
    if not habilitado():
        return None

    base_url = getattr(config, "GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": getattr(config, "GROQ_MODEL", "openai/gpt-oss-20b"),
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=getattr(config, "GROQ_TIMEOUT_SEGUNDOS", 20),
        )
        if response.status_code != 200:
            logger.debug(f"Groq respondio HTTP {response.status_code}: {response.text[:300]}")
            return None
        datos = response.json()
    except Exception as e:
        logger.debug(f"Groq no disponible: {e}")
        return None

    try:
        contenido = datos["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    return _json_desde_texto(contenido)


def _deduplicar(items: list[str]) -> list[str]:
    vistos = set()
    salida = []
    for item in items:
        limpio = re.sub(r"\s+", " ", str(item or "").strip())
        if not limpio:
            continue
        clave = limpio.lower()
        if clave in vistos:
            continue
        vistos.add(clave)
        salida.append(limpio)
    return salida


@lru_cache(maxsize=256)
def generar_queries(equipo1: str, equipo2: str) -> tuple[str, ...]:
    """Genera queries extra para indexadores configurados."""
    if not getattr(config, "GROQ_GENERAR_QUERIES", True):
        return ()

    system = (
        "Sos un asistente que mejora busquedas de archivos de partidos completos. "
        "No inventes URLs ni sitios. Devolve solo JSON valido."
    )
    user = json.dumps(
        {
            "tarea": "generar_queries_busqueda",
            "restricciones": [
                "Solo queries de texto para indexadores ya configurados por el usuario",
                "Priorizar 720p, partido completo, Mundial 2026",
                "Incluir variantes en ingles y espanol",
                "No incluir URLs, dominios ni instrucciones de descarga",
            ],
            "partido": {"equipo1": equipo1, "equipo2": equipo2},
            "formato_respuesta": {"queries": ["string"]},
            "max_queries": getattr(config, "GROQ_MAX_QUERIES", 6),
        },
        ensure_ascii=False,
    )
    datos = _chat_json(system, user)
    queries = datos.get("queries", []) if isinstance(datos, dict) else []
    max_queries = getattr(config, "GROQ_MAX_QUERIES", 6)
    return tuple(_deduplicar(queries)[:max_queries])


def clasificar_resultados(equipo1: str, equipo2: str, resultados: list[dict]) -> list[dict]:
    """
    Ajusta resultados con una opinion de Groq, manteniendo score deterministico.

    Devuelve la misma lista, posiblemente con campos groq_* y puntuacion ajustada.
    """
    if (
        not resultados
        or not getattr(config, "GROQ_CLASIFICAR_RESULTADOS", True)
        or not habilitado()
    ):
        return resultados

    limite = getattr(config, "GROQ_MAX_RESULTADOS_CLASIFICAR", 12)
    muestra = resultados[:limite]
    payload_resultados = [
        {
            "indice": i,
            "titulo": r.get("titulo"),
            "fuente": r.get("fuente"),
            "seeders": r.get("seeders"),
            "tamano_gb": r.get("tamano_gb"),
            "puntuacion_actual": r.get("puntuacion"),
        }
        for i, r in enumerate(muestra)
    ]

    system = (
        "Sos un clasificador conservador de resultados de busqueda. "
        "No inventes disponibilidad ni enlaces. Solo evalua los titulos dados. "
        "Devolve JSON valido."
    )
    user = json.dumps(
        {
            "tarea": "clasificar_resultados_partido",
            "partido": {"equipo1": equipo1, "equipo2": equipo2},
            "preferencias": {
                "idioma_final": "es",
                "resolucion_preferida": "720p",
                "tamano_ideal_gb": "1.5-5",
                "descartar_resumenes": True,
            },
            "resultados": payload_resultados,
            "formato_respuesta": {
                "resultados": [
                    {
                        "indice": 0,
                        "ajuste_puntuacion": 0,
                        "idioma": "es|en|desconocido",
                        "partido_completo": True,
                        "descartar": False,
                        "razon": "string",
                    }
                ]
            },
        },
        ensure_ascii=False,
    )
    datos = _chat_json(system, user)
    clasificados = datos.get("resultados", []) if isinstance(datos, dict) else []
    if not isinstance(clasificados, list):
        return resultados

    por_indice = {}
    for item in clasificados:
        if not isinstance(item, dict):
            continue
        try:
            indice = int(item.get("indice"))
        except (TypeError, ValueError):
            continue
        por_indice[indice] = item

    for indice, item in por_indice.items():
        if indice < 0 or indice >= len(muestra):
            continue
        resultado = muestra[indice]
        try:
            ajuste = max(min(float(item.get("ajuste_puntuacion", 0)), 40), -80)
        except (TypeError, ValueError):
            ajuste = 0
        if item.get("descartar"):
            ajuste = min(ajuste, -80)
        resultado["puntuacion"] = resultado.get("puntuacion", 0) + ajuste
        resultado["groq_ajuste"] = ajuste
        resultado["groq_idioma"] = item.get("idioma")
        resultado["groq_descartar"] = bool(item.get("descartar"))
        resultado["groq_razon"] = item.get("razon")

    return resultados
