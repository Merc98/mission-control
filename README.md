# Mission Control CLI

CLI coordinador multiagente para `codex`, `gemini`, `qwen`.

## Instalación

```powershell
cd "C:\Users\beloc\CLI Workspace\nfc\mission-control-cli"
python .\mission_control.py discover
```

Opcional instalar CLIs:

```powershell
python .\mission_control.py install all
```

## Uso rápido

```powershell
python .\mission_control.py discover
python .\mission_control.py status
python .\mission_control.py dispatch all "Objetivo: compilar APK, instalar, validar funciones"
python .\mission_control.py cancel
```

## Bridge

Por defecto usa:

`C:\Users\beloc\CLI Workspace\nfc\cli-bridge`

Puedes cambiarlo:

```powershell
python .\mission_control.py --bridge "D:\otro\bridge" status
```

## Procedimiento operativo en GitHub

1. Clonar repo
2. Ejecutar `discover`
3. Ejecutar `install all` si falta algún CLI
4. Lanzar agentes en terminales separadas
5. Usar `dispatch all` para instrucciones
6. Monitorear con `status`
7. Cancelar con `cancel` cuando necesites
