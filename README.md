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
python mission_control.py debug
python mission_control.py catalog list --kind skill
python mission_control.py catalog install autoagent --target global
python mission_control.py component list --kind agent
python mission_control.py agent config-set --agent-id autoagent --key mode --value autonomous
python mission_control.py policy set --key approval_required.security --value true
python mission_control.py policy list
python mission_control.py approval request --action "run_security_scan" --scope "scope-001" --risk high --by operator
python mission_control.py approval decide --id <approval_id> --decision approved --by lead --note "authorized window"
python mission_control.py event emit --type source.received --source github --body-json '{"repo":"org/repo"}'
```

## Estructura

- `mission_control.py`: CLI + orchestration local + discovery + SQLite
- `web/index.html`: UI local estilo Mission Control (navy background, sidebar, whiteboard fijo)
- `mission-control.ps1`: wrapper para PowerShell

## Configuración local

Al ejecutar `config` o `start`, se inicializa `~/.agentforge/config.toml` (o `$AGENTFORGE_HOME/config.toml`) con token local.

## Estado de implementación por módulo

Por defecto usa `CLI_BRIDGE_HOME` si existe. Si no existe, usa:

`~/.mission-control/cli-bridge`

Este commit prioriza la **base MVP operativa** y la estructura de comandos para iterar rápido hacia v0.2+.

## Debug recomendado

Para validar que todo esté fluido localmente:

```bash
python mission_control.py debug
```

El comando revisa carpetas bridge, SQLite, config TOML, discovery de endpoints locales y presencia de CLIs, y luego devuelve recomendaciones accionables.

## Diferenciación clara: Skill vs Plugin vs MCP vs Agent

- **Agent**: runtime/autómata completo (ejecuta tareas end-to-end).
- **Skill**: conocimiento/flujo reutilizable (prompting/procedimiento).
- **Plugin**: herramienta extensible ejecutable (scripts/integraciones).
- **MCP**: servidor/contexto externo conectable para capacidades y datos.

La app ahora incorpora:
- `catalog list` para búsqueda filtrada por tipo/categoría/texto.
- `catalog install` para instalación automática por catálogo con scope:
  - global
  - por agente (`agent:<id>`)
- `component list` para ver qué quedó instalado y en qué scope.
- `agent config-set` para configurar cada agente desde raíz (también invocable por LLM/chat vía CLI).

## Mejoras estratégicas aplicadas (control plane)

Para alinear la app con una arquitectura de control plane multiagente:

- **Event log operativo** (`event emit`) con taxonomía extensible (`source.received`, `approval.requested`, etc.).
- **Approval gates** (`approval request/decide`) para tareas sensibles.
- **Policy registry** (`policy set/list`) para reglas de operación y seguridad.

Estos tres bloques permiten construir una transición ordenada hacia:
- API-first + WebSockets + workers asíncronos.
- Human-in-the-loop y auditoría por línea de tiempo.
- Gobernanza por políticas antes de ampliar módulos OSINT/pentesting.
