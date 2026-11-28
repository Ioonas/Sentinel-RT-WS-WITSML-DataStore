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
