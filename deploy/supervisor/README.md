# Supervisor de servicios

El supervisor (`python -m sentinel.bootstrap.supervisor`) levanta la API WITSML y
administrativa y el worker de correo, y los relanza cuando terminan. Un reinicio
pedido desde el panel termina el proceso correspondiente tras esperar a que sus
operaciones en curso acaben (hasta 5 minutos); el supervisor lo vuelve a levantar.

## Linux (systemd)

```bash
sudo cp deploy/supervisor/sentinel-supervisor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sentinel-supervisor
```

## Windows (NSSM)

Usar [NSSM](https://nssm.cc) para registrar el supervisor como servicio de Windows.
Desde una consola con permisos de administrador, con el entorno virtual del proyecto:

```bat
nssm install SentinelSupervisor "C:\sentinel\.venv\Scripts\python.exe" "-m" "sentinel.bootstrap.supervisor"
nssm set SentinelSupervisor AppDirectory "C:\sentinel"
nssm set SentinelSupervisor AppStdout "C:\sentinel\logs\supervisor.log"
nssm set SentinelSupervisor AppStderr "C:\sentinel\logs\supervisor.log"
nssm set SentinelSupervisor AppExit Default Restart
nssm start SentinelSupervisor
```

Las variables de entorno (`SENTINEL_*`) deben estar disponibles para el servicio
(en NSSM: `nssm set SentinelSupervisor AppEnvironmentExtra ...`).

## Servicio por servicio

Para levantar solo uno: `python -m sentinel.bootstrap.supervisor api` o
`python -m sentinel.bootstrap.supervisor mail-worker`.

## Servicios y puertos

El supervisor levanta tres procesos:

| Servicio | Qué sirve | Puerto (por defecto) |
|---|---|---|
| `witsml` | Store API WMLS (`/witsml`) | 50101 (interno) |
| `admin` | API administrativa (`/admin-api/v1`) y panel | 50100 |
| `mail-worker` | Cola de correo | — |

Cada uno tiene su propio botón de reinicio en el panel.

### nginx

El WITSML queda detrás de nginx en la misma URL pública que ya usan los clientes.
Enruta `/witsml` al proceso WITSML y el resto al administrativo:

```nginx
location /witsml {
    proxy_pass http://127.0.0.1:50101;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 20m;
}

location / {
    proxy_pass http://127.0.0.1:50100;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Ajusta los puertos si cambiaste `SENTINEL_ADMIN_PORT` o `SENTINEL_WITSML_PORT`.
El panel sigue apuntando a `SENTINEL_API_URL=http://127.0.0.1:50100`.
