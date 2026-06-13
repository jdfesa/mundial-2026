# Funcionamiento

Este documento concentra las reglas operativas del descargador: cuando busca, como decide
que descargar, como maneja idioma, historial, verificacion local y postproceso.

## Logica De Busqueda

El script revisa el calendario y solo procesa partidos que:

- ya hayan empezado hace al menos 3 horas;
- no esten descargados en idioma final;
- no hayan superado el maximo de intentos normales;
- respeten el tiempo entre reintentos.

Para cada partido genera queries en ingles y espanol, en ambos ordenes:

```text
Mexico vs South Africa
South Africa vs Mexico
Mexico vs Sudafrica
Sudafrica vs Mexico
```

Busca primero en fuentes manuales y luego en los indexadores configurados en
`fuentes_torrent.json`. Si no encuentra nada, `yt-dlp` queda reservado como fallback tardio
y validado.

Si `GROQ_HABILITADO=1`, Groq puede sumar queries de busqueda y ajustar la puntuacion de
resultados ya encontrados. No agrega URLs por su cuenta ni salta las fuentes configuradas.

## Ranking De Resultados

El mejor resultado se elige por puntuacion aproximada:

- Idioma espanol: +100 puntos
- Partido completo: +50
- Calidad 720p: +30
- Seeders: hasta +40
- Tamano ideal, entre 1.5 GB y 5 GB: +15
- Keywords del mundial: +10

El objetivo es priorizar partido completo, idioma espanol, 720p razonable y tamano esperable
sin gastar CPU en recomprimir por defecto.

## Fallback yt-dlp

El fallback `yt-dlp` espera bastante mas que los torrents antes de activarse
(`YTDLP_HORAS_ESPERA_POST_PARTIDO`, por defecto 24 horas desde el inicio del partido).

Antes de descargar, revisa metadata:

- ambos equipos deben aparecer en el titulo;
- debe haber senal de partido completo o replay;
- no puede contener palabras de comentario, reaccion o resumen;
- debe durar entre 90 y 180 minutos;
- debe tener al menos 720p.

Si un archivo descargado por `yt-dlp` no pasa esa validacion local, queda como `rechazado`
y el partido vuelve a pendiente.

## Logica De Idioma

| Idioma detectado | Estado | Sigue buscando |
|------------------|--------|----------------|
| Espanol | `FINAL` | No, ya tiene la version preferida. |
| Ingles | `MEJORABLE` | Si, pero solo si encuentra una en espanol. |
| Desconocido | `MEJORABLE` | Si, igual que ingles. |

Si un partido ya esta en ingles y una busqueda posterior encuentra otro resultado en ingles,
no se vuelve a descargar. Si encuentra una version en espanol, se descarga y el partido pasa
a estado final.

Las busquedas de mejora para partidos ya descargados en ingles no consumen los intentos
normales. Se registran aparte como `intentos_mejora` y `ultimo_intento_mejora`, y se
reintentan segun `MINUTOS_ENTRE_REINTENTOS_MEJORA`.

## Historial Y Verificacion Local

El historico operativo vive en `estado_descargas.json`. Ese archivo es la verdad que usa el
script para saber que partidos ya fueron descargados, cuales son finales y cuales siguen
siendo mejorables.

La biblioteca local solo se usa como verificacion complementaria. Si moves o borras un
archivo de esta computadora despues de pasarlo a otra PC, el partido no vuelve a pendiente.

En cada `--status` y al final de una ejecucion real, el script revisa la biblioteca local:

- busca archivos de video en `DIRECTORIO_BASE`;
- tambien revisa la ruta guardada del partido si existe;
- opcionalmente revisa rutas extra configuradas en `MUNDIAL_DIRECTORIOS_EXTRA`;
- si encuentra un video, guarda metadata local;
- si ya no encuentra el video, conserva `archivo_local_ultimo` y marca
  `archivo_local_estado=movido_o_borrado`.

Para leer duracion, resolucion e idioma de pistas de audio usa `ffprobe` si esta instalado.
Si no esta, igual detecta existencia y tamano.

## Nombres Y Postproceso

Los archivos completos se renombran a un formato estable cuando el script puede hacerlo de
forma segura:

```text
001_mexico_vs_sudafrica_en.mkv
002_corea_del_sur_vs_rep_checa_es.mp4
```

El prefijo numerico evita colisiones, los equipos salen del calendario en espanol y el
sufijo indica idioma/estado: `_es` es final, `_en` queda como mejorable.

Si qBittorrent esta administrando el archivo, el renombrado se intenta por la Web API de
qBittorrent. Cuando el torrent trae una carpeta release con spam, el video principal se
aplana a la raiz del grupo con el nombre canonico. Para fuentes manuales o `yt-dlp`, el
renombrado puede hacerse directamente sobre el archivo.

Despues de verificar el archivo local, el flujo puede generar una copia MP4 compatible con
el reproductor del navegador. Esto esta pensado para que `index.html` funcione como una
experiencia simple tipo YouTube en Chrome:

- si el origen ya es MP4 con audio compatible, se usa tal cual;
- si el origen trae video H.264 y audio no compatible para Chrome, por ejemplo AC3 en MKV,
  se copia el video sin recomprimir y solo se convierte el audio a AAC;
- si no hay espacio libre suficiente, queda `compatibilidad_web=pendiente` y se reintenta
  en una corrida futura;
- por defecto conserva el archivo original para no romper torrents que siguen seedeando.

El comando manual para preparar la biblioteca existente sin buscar descargas nuevas es:

```bash
./run.sh --postprocesar-web
```

Variables relacionadas:

```env
WEB_COMPAT_POSTPROCESO=1
WEB_COMPAT_AUDIO_BITRATE=192k
WEB_COMPAT_AUDIO_CHANNELS=2
WEB_COMPAT_MIN_FREE_GB=1.0
WEB_COMPAT_CONSERVAR_ORIGINAL=1
WEB_COMPAT_RETIRAR_TORRENT_ORIGINAL=1
```

`WEB_COMPAT_CONSERVAR_ORIGINAL=0` elimina el origen despues de generar el MP4, pero puede
dejar qBittorrent con archivos faltantes si el torrent seguia activo. Con
`WEB_COMPAT_RETIRAR_TORRENT_ORIGINAL=1`, el flujo intenta retirar primero el torrent de
qBittorrent sin pedirle que borre archivos, y luego elimina solo el MKV original. Usalo solo
si ya no necesitas seedear ese torrent.

Ademas se conserva una evaluacion de tamano/resolucion:

- hasta 5 GB y 720p o menos: `mantener_origen`;
- mas de 5 GB o por encima de 720p: `revisar`.

## Sincronizacion Con qBittorrent

Cuando una descarga se encola, el estado guarda `descarga_iniciada_en`,
`revisar_descarga_despues_de` y `torrent_hash` si esta disponible.

La revision de una hora es una referencia: cada corrida consulta qBittorrent y solo
mueve/renombra/verifica cuando el progreso real esta completo.

Si qBittorrent esta corriendo y la Web API responde, tambien sincroniza torrents completos:

- detecta torrents ya completados;
- los compara contra el calendario/estado por titulo y equipos;
- si estan en la carpeta por defecto de qBittorrent, le pide a qBittorrent que los mueva al
  destino final por fase/grupo;
- renombra el video principal al formato canonico en la raiz del grupo;
- opcionalmente limpia auxiliares pequenos de spam (`.nfo`, `.txt`, `.url`);
- genera MP4/AAC para el indice HTML cuando el audio del origen no es compatible con
  navegador;
- no mueve archivos con `shutil` mientras qBittorrent los administra.

Esto se controla con:

```env
QBIT_MOVER_COMPLETADOS=1
QBIT_BUSCAR_TODAS_LAS_DESCARGAS=1
MUNDIAL_RENOMBRAR_ARCHIVOS=1
QBIT_LIMPIAR_AUXILIARES=1
```

## Reportes Generados

Tambien se generan:

```text
estado_partidos.txt
reporte_diario.txt
<DIRECTORIO_BASE>/index.html
<DIRECTORIO_BASE>/playlist_mundial.m3u
```

El indice HTML permite abrir los partidos descargados desde una pagina simple, agrupados por
grupo/fase. La playlist M3U sirve para abrir todo desde VLC u otro reproductor compatible.

La zona horaria del reporte diario se puede cambiar con:

```env
MUNDIAL_ZONA_HORARIA=America/Argentina/Buenos_Aires
```
