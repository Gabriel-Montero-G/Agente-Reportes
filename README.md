# Agente de Generación de Informes

## Qué es

Una aplicación web basada en FastAPI + LangChain que genera informes sobre cualquier tema usando un agente ReAct autónomo. El usuario escribe preguntas en el chat de la izquierda mientras el informe en generación se muestra en tiempo real en el panel derecho. El agente utiliza Tavily como fuente de búsqueda en internet y OpenRouter para invocar modelos de lenguaje de código abierto, coordinando múltiples pasos de investigación, síntesis y refinamiento hasta producir un informe de alta calidad.

## Requisitos

- **Python 3.11+** — requerido para la sintaxis de tipos y características async.
- **Clave de OpenRouter** — libre en https://openrouter.ai/keys (20 req/min, 50 req/día en tier gratuito).
- **Clave de Tavily** — libre en https://app.tavily.com (1000 créditos/mes).

## Instalación

Abre PowerShell en el directorio del proyecto y ejecuta:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Luego edita `.env` con tus claves:

```env
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx
TAVILY_API_KEY=tvly-xxxxxxxx
MODEL_ID=nvidia/nemotron-3-ultra-550b-a55b:free
```

## Ejecución

Con el entorno virtual activado, ejecuta:

```powershell
uvicorn app.server:app --reload --port 8000
```

Luego abre http://127.0.0.1:8000 en tu navegador.

## Límites de cuota

**OpenRouter (tier gratuito):**
- 20 peticiones por minuto
- 50 peticiones por día
- El agente está configurado con `max_iterations=6`, lo que limita cada informe a aproximadamente 6 peticiones. Esto permite unos 8 informes completos por día.

**Tavily (tier gratuito):**
- 1000 créditos por mes

## Uso

1. Escribe un tema o pregunta en el chat (ejemplo: "¿Cuáles son los últimos avances en IA?").
2. El agente investigará, buscará en internet y generará un informe.
3. Refina el resultado con mensajes adicionales:
   - "Amplía la sección 2"
   - "Añade datos de 2025"
   - "Explica el concepto X"
4. Descarga el informe finalizado usando el botón de descarga.

## Tests

**Tests sin red (por defecto):**
```powershell
pytest
```

**Tests con APIs reales (gasta cuota):**
```powershell
pytest -m live
```

Hay 50 tests offline que validan lógica, configuración y manejo de errores. Un test live opcional valida la integración completa con OpenRouter y Tavily.

## Límites conocidos

- **Sin persistencia:** al reiniciar el servidor, todas las sesiones se pierden.
- **Sin autenticación:** no hay control de acceso; cualquiera que pueda alcanzar el puerto local puede leer el informe de cualquier sesión vía `GET /api/report/{session_id}` si adivina u observa el `session_id`. Cada pestaña sí tiene su propia sesión aislada (`session_id` vive en `sessionStorage`, por pestaña), pero esto no es apto para un entorno multi-tenant sin confianza mutua entre usuarios.
- **Sin exportación a PDF:** solo se descarga en formato Markdown.
- **AgentExecutor en mantenimiento:** LangChain marcó `AgentExecutor` como deprecated desde la v1.0, por lo que se fija `langchain<1.0` en requirements.txt.
