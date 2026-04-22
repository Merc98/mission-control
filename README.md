# AgentForge Mission Control (Blueprint MVP scaffold)

Este repositorio ahora implementa un **scaffold funcional** alineado con el blueprint de AgentForge Mission Control:

- CLI principal `agentforge` (archivo `mission_control.py`)
- Dashboard web local (archivo `web/index.html`)
- Persistencia local en SQLite para misiones/equipos
- Descubrimiento de modelos en Ollama y LM Studio
- Bridge de mensajes entre agentes (inbox/outbox/state)

## Comandos clave

```bash
python mission_control.py start
python mission_control.py agents list
python mission_control.py mission new --name "MVP" --objective "Levantar hub"
python mission_control.py team create --name "alpha" --members orchestrator specialist validator
python mission_control.py termux pair
python mission_control.py mcp load
python mission_control.py config
```

## Estructura

- `mission_control.py`: CLI + orchestration local + discovery + SQLite
- `web/index.html`: UI local estilo Mission Control (navy background, sidebar, whiteboard fijo)
- `mission-control.ps1`: wrapper para PowerShell

## Configuración local

Al ejecutar `config` o `start`, se inicializa `~/.agentforge/config.toml` (o `$AGENTFORGE_HOME/config.toml`) con token local.

## Estado de implementación por módulo

- ✅ Mission Control Hub (UI scaffold + métricas mock)
- ✅ Agent Registry (detección CLI + Ollama/LM Studio)
- ✅ Whiteboard (panel siempre visible, feed inicial)
- ✅ Team Builder (creación de equipos en SQLite)
- 🟡 Termux Bridge (pairing checklist inicial)
- 🟡 MCP Loader (carga base vía config, parsing avanzado pendiente)
- ⏳ Social Bridge / Cloud & Containers / CyberStrike (pendiente)

## Notas

Este commit prioriza la **base MVP operativa** y la estructura de comandos para iterar rápido hacia v0.2+.
