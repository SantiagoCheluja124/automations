# Catálogo de workflows

Generado automáticamente por `scripts/sanitize.py`.

| # | Archivo | Nodos | Disparador | Llama a | Credenciales |
|---|---|---|---|---|---|
| 01 | `01_first_flow.json` | 25 | webhook | buffer_memory, first_message | googleApi<br>httpCustomAuth<br>openAiApi<br>twilioApi |
| 02 | `02_first_message.json` | 11 | executeWorkflowTrigger | alt_segment | googleApi<br>httpCustomAuth<br>postgres (BD principal, solo lectura) |
| 03 | `03_buffer_memory.json` | 9 | executeWorkflowTrigger | agente_orquestador | redis |
| 04 | `04_agente_orquestador.json` | 20 | executeWorkflowTrigger | ESCALATE_HUMAN, FALLBACK, IMG_subflujo, ROUTE_BY_STATE, UNSAFE, clasificar_intencion, event, tokens | googleApi<br>openAiApi |
| 05 | `05_ROUTE_BY_STATE.json` | 17 | executeWorkflowTrigger | PAID_OFF, actived_loan, clasificar_intencion, event | openAiApi<br>postgres (BD principal, solo lectura) |
| 06 | `06_actived_loan.json` | 11 | executeWorkflowTrigger | clasificar_intencion, event | httpCustomAuth<br>postgres (data warehouse, solo lectura) |
| 07 | `07_PAID_OFF.json` | 11 | executeWorkflowTrigger | clasificar_intencion, event | httpCustomAuth<br>postgres (BD principal, solo lectura) |
| 08 | `08_event.json` | 32 | executeWorkflowTrigger | tokens | anthropicApi<br>googleApi<br>httpCustomAuth<br>openAiApi<br>postgres (BD de Chatwoot)<br>postgres (BD principal, solo lectura) |
| 09 | `09_IMG_subflujo.json` | 6 | executeWorkflowTrigger | event | postgres (BD principal, solo lectura) |
| 10 | `10_ESCALATE_HUMAN.json` | 16 | executeWorkflowTrigger | - | googleApi<br>httpCustomAuth |
| 11 | `11_FALLBACK.json` | 2 | executeWorkflowTrigger | - | httpCustomAuth |
| 12 | `12_UNSAFE.json` | 5 | executeWorkflowTrigger | - | httpCustomAuth |
| 13 | `13_clasificar_intencion.json` | 7 | executeWorkflowTrigger | event, tokens | openAiApi |
| 14 | `14_tokens.json` | 12 | executeWorkflowTrigger | - | googleApi<br>n8nApi (API de la propia instancia de n8n) |
| 15 | `15_alt_segment.json` | 8 | executeWorkflowTrigger | - | googleApi<br>httpCustomAuth |
| 20 | `20_status_agent.json` | 7 | scheduleTrigger | - | googleApi<br>httpCustomAuth |
| 21 | `21_archive_data_tables.json` | 15 | scheduleTrigger | - | googleApi |
| 22 | `22_daily_metrics.json` | 35 | scheduleTrigger | - | googleApi<br>postgres (BD de Chatwoot) |
| 23 | `23_dashboard.json` | 13 | webhook | - | googleApi |
