# Archivos Locales

Este proyecto separa el codigo versionado de los datos locales. La idea es que el repo sea
reproducible sin subir credenciales, mirrors personales, URLs privadas, historial operativo
ni archivos generados por cada maquina.

## Crear La Configuracion Local

Despues de clonar el repo, crea los archivos locales desde sus templates:

```bash
cp .env.example .env
cp fuentes_torrent.example.json fuentes_torrent.json
cp fuentes_manuales.example.json fuentes_manuales.json
```

Luego edita:

- `.env`: rutas locales, qBittorrent, Groq opcional y parametros del fallback.
- `fuentes_torrent.json`: mirrors reales de indexadores que quieras usar.
- `fuentes_manuales.json`: URLs puntuales que tengas permiso de descargar.

## Archivos Que No Se Suben

| Archivo | Se crea como | Por que no se sube |
|---------|--------------|--------------------|
| `.env` | Copia manual de `.env.example` | Contiene rutas, credenciales locales y API keys. |
| `fuentes_torrent.json` | Copia manual de `fuentes_torrent.example.json` | Contiene mirrors reales; conviene no publicarlos ni atar el repo a URLs cambiantes. |
| `fuentes_manuales.json` | Copia manual de `fuentes_manuales.example.json` | Puede contener URLs privadas, temporales o propias del usuario. |
| `estado_descargas.json` | Lo genera el script | Es el historial local que evita depender de archivos ya movidos o borrados. |
| `estado_partidos.txt` | Lo genera el script | Es un resumen legible del estado actual. |
| `reporte_diario.txt` | Lo genera `reporte_diario.py` | Cambia con cada ejecucion y cada calendario. |
| `mundial.log` | Lo genera el script | Contiene logs locales de ejecucion. |
| `launchd_stdout.log` / `launchd_stderr.log` | Los genera launchd | Son logs locales de macOS. |
| `Mundial_Partidos/` | Lo genera el flujo de descarga | Contiene videos y archivos pesados. |
| `com.mundial.descargador.plist` | Lo genera el instalador macOS | Contiene rutas absolutas de la maquina. |

## Templates Versionados

Estos archivos si viven en el repo y documentan la forma esperada de cada configuracion:

- `.env.example`
- `fuentes_torrent.example.json`
- `fuentes_manuales.example.json`

Si agregas una nueva variable o cambia el formato de una fuente, actualiza primero el
`.example` correspondiente. El archivo real local queda fuera de git.

## Historial De Descargas

`estado_descargas.json` es importante: es la memoria del script. Permite que el proceso sepa
que un partido ya fue descargado aunque el archivo ya no exista en esta computadora.

No hace falta crearlo a mano. Si no existe, el script lo inicializa. Borrarlo equivale a
reiniciar la memoria operativa del proyecto, asi que el script podria volver a intentar
partidos que ya habias procesado.

## Resumen Rapido

- Configuracion que editas vos: `.env`, `fuentes_torrent.json`, `fuentes_manuales.json`.
- Estado que genera el sistema: `estado_descargas.json`, `estado_partidos.txt`, `reporte_diario.txt`, `mundial.log`.
- Archivos grandes: siempre fuera de git, dentro de `Mundial_Partidos/` o la ruta configurada.
