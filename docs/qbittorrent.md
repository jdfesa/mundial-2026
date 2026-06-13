# qBittorrent

qBittorrent es el punto de integracion principal para encolar descargas, consultar progreso,
mover torrents completos, renombrar archivos administrados por el cliente y limpiar
auxiliares de spam cuando corresponde.

## Web API

La descarga intenta primero la Web API (`host:puerto`). Si la Web API no responde, se usa un
fallback que abre el magnet link directamente con la aplicacion asociada del sistema:

- macOS: `open`
- Windows: `cmd /c start`
- Linux: `xdg-open`

En `--status` el script no abre aplicaciones por su cuenta: solo consulta la Web API. Si
qBittorrent esta abierto pero la Web UI esta deshabilitada o en otro puerto, el estado lo
informa como Web API no disponible, no como descarga fallida.

## Configuracion Recomendada

En qBittorrent:

1. Abrir qBittorrent.
2. Ir a Preferencias > Web UI > Habilitar la interfaz de usuario web.
3. Configurar:
   - IP address: `127.0.0.1`
   - Port: `8080`
   - Username: `admin`
   - Password: `adminadmin`
4. Dejar desactivado HTTPS para uso local.
5. Tocar Apply/OK y reiniciar qBittorrent si el puerto no responde.
6. Verificar que `.env` tenga los mismos valores.

En `.env`:

```env
QBIT_HOST=127.0.0.1
QBIT_PORT=8080
QBIT_USER=admin
QBIT_PASS=adminadmin
QBIT_LIMPIAR_AUXILIARES=1
```

Con `QBIT_LIMPIAR_AUXILIARES=1`, el script marca como no descargables y elimina auxiliares
pequenos conocidos (`.nfo`, `.txt`, `.url`) despues de mover el video principal a la raiz
del grupo. No toca subtitulos ni archivos de extension desconocida.

## Prueba Rapida

```bash
curl -I http://127.0.0.1:8080
```

Si responde `401`, `403` o `200`, la Web UI esta levantada. Si responde `000` o connection
refused, qBittorrent no esta escuchando en ese puerto o falta aplicar la configuracion.

Para probar desde el script:

```bash
./run.sh --status
```

La salida esperada, si conecta, incluye algo como:

```text
Conectado a qBittorrent v5.0.4
```

## Nota Sobre Sandboxes

Algunos entornos sandboxeados pueden no ver procesos locales o no poder conectarse a
`127.0.0.1:8080`, aunque qBittorrent este abierto en la maquina real. En ese caso, probar
desde una terminal normal ayuda a separar un problema de configuracion real de una
limitacion del entorno.
