# AgentForge Mission Control - Strategic Plan (v0.2 baseline)

## Objetivo
Evolucionar de scaffold CLI/UI a **control plane orientado a eventos** con aprobaciones humanas, políticas y trazabilidad.

## Backbone recomendado
- API-first (FastAPI + WebSockets)
- Queue/streams para jobs asíncronos
- Workers aislados (browser/scraper/research/security)
- Fuente de verdad operativa en DB transaccional
- Auditoría y evidencia por artefacto + timeline

## Taxonomía inicial de eventos
- `source.received`
- `job.enqueued`
- `job.started`
- `artifact.created`
- `approval.requested`
- `approval.approved`
- `approval.rejected`
- `alert.raised`
- `route.denied`
- `report.exported`

## Gobierno y seguridad (mínimo)
- Approval gate obligatorio para acciones sensibles
- Policy registry para reglas de alcance
- Scope registry previo a módulos de seguridad
- Modo OSINT pasivo por defecto

## Roadmap corto (10-12 semanas)
1. Event bus + timeline/whiteboard persistente
2. Inbox universal + triage dev/CI
3. Router de modelos local/nube
4. Scope + approvals + auditoría inmutable
5. Watchlists OSINT pasivas
6. Runners aislados para módulos de mayor riesgo
