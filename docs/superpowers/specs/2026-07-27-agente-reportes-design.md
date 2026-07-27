# Agente de generación de reportes — Diseño

**Fecha:** 2026-07-27
**Estado:** aprobado, pendiente de plan de implementación

## Problema

Producir un brief de investigación sobre cualquier tema exige buscar fuentes, leerlas y sintetizarlas. Se busca una aplicación local donde el usuario escriba un tema en un chat, un agente investigue en la web y publique un brief de una página en un panel contiguo, refinable por conversación.

## Alcance

Una aplicación web local de un solo usuario, con dos paneles: chat a la izquierda, brief a la derecha. El agente investiga con Tavily y redacta con un modelo gratuito de NVIDIA servido por OpenRouter. El brief es el artefacto vivo de la sesión: el usuario pide cambios por chat ("amplía la sección 2", "agrega datos de 2025") y el panel se actualiza.

**Fuera de alcance:** autenticación, multiusuario, persistencia en disco o base de datos, exportación a PDF, historial de reportes anteriores.

## Restricciones que dominan el diseño

**El tier gratuito de OpenRouter permite 20 peticiones por minuto y 50 por día** (sube a 1000/día solo si la cuenta compró ≥$10 en créditos en algún momento). Cada iteración del agente consume una petición. Este límite condiciona los topes del executor, el prompt de sistema y el manejo de errores.

**Modelo:** `nvidia/nemotron-3-ultra-550b-a55b:free` — 1M de contexto, soporta tool calling nativo. Es el único modelo NVIDIA gratuito de OpenRouter apto: `nvidia/nemotron-3.5-content-safety:free` es un guardrail sin soporte de herramientas, y `nvidia/nemotron-3-ultra-550b-a55b` (sin sufijo) es de pago.

**Tavily** en su tier gratuito ofrece 1000 créditos mensuales.

## Decisiones de diseño

| Decisión | Elección | Razón |
|---|---|---|
| Arquitectura del agente | ReAct con `AgentExecutor` | Elegida por el usuario sobre un pipeline determinista, por flexibilidad ante temas variados |
| Framework | LangChain puro, sin LangGraph | Requisito explícito del usuario |
| Construcción del agente | `create_tool_calling_agent` | El modelo soporta tools nativas; evita el parseo frágil de `Thought:/Action:` del ReAct textual |
| Interfaz | FastAPI + HTML/JS vanilla | Control del layout de dos paneles y del streaming, sin paso de build |
| Persistencia | Ninguna, todo en memoria | Alcance mínimo; descarga `.md` para lo que valga la pena guardar |
| Extensión del reporte | Brief de 300-600 palabras | Barato en tokens, permite iterar dentro de la cuota diaria |
| Idioma | Español | Idioma de trabajo del usuario |

`AgentExecutor` está en modo mantenimiento en LangChain — la documentación oficial recomienda LangGraph. Es estable y funciona, pero no recibirá evolución. Se asume conscientemente.

## Arquitectura

```
Navegador (index.html + app.js)
   │  POST /api/chat  (SSE: token, step, step_done, report, error, done)
   ▼
FastAPI (server.py)
   │  astream_events
   ▼
RunnableWithMessageHistory
   └── AgentExecutor (max_iterations=6, max_execution_time=120)
         ├── ChatOpenAI ──► OpenRouter ──► nemotron-3-ultra-550b-a55b:free
         └── tools
              ├── tavily_search(query)      ──► Tavily API
              └── write_report(markdown)    ──► SessionStore
```

### Componentes

**`config.py`** — Carga y valida variables de entorno al arrancar. Si falta `OPENROUTER_API_KEY` o `TAVILY_API_KEY`, el servidor no levanta y lo dice. Expone `MODEL_ID` (por defecto `nvidia/nemotron-3-ultra-550b-a55b:free`).

**`llm.py`** — Construye el `ChatOpenAI` apuntado a `https://openrouter.ai/api/v1` con `streaming=True`. Único punto donde se configura el proveedor.

**`session.py`** — Store en memoria: diccionario `session_id → Session`. Cada `Session` tiene el `InMemoryChatMessageHistory` y el markdown del reporte actual. Sin TTL ni limpieza: el proceso muere y todo desaparece, que es el comportamiento deseado.

**`tools.py`** — Dos herramientas:

- `tavily_search(query: str) -> str`: envuelve `TavilySearch` de `langchain-tavily`. Captura toda excepción y devuelve `"La búsqueda falló: <motivo>"`. En ReAct un fallo de herramienta es una observación para el agente, no un error del servidor.
- `make_write_report(session) -> Tool`: factory que devuelve `write_report(markdown: str)` cerrada sobre la sesión. Escribe el markdown en `session.report` y devuelve `"Reporte actualizado."` al agente.

**`agent.py`** — `build_agent(session)` compone el prompt de sistema, `create_tool_calling_agent`, `AgentExecutor` y `RunnableWithMessageHistory`. Se construye **por sesión**, no globalmente: componer runnables es barato y así `write_report` escribe siempre en la sesión correcta, sin estado compartido entre pestañas.

**`server.py`** — FastAPI. Sirve los estáticos y expone los endpoints. Traduce los eventos de `astream_events` a eventos SSE.

### La herramienta `write_report`

El agente publica el brief **llamando a una herramienta**, no escribiéndolo en su respuesta final. Esto separa sin ambigüedad la conversación del artefacto: el chat lleva el diálogo ("busqué X, encontré Y, ¿profundizo?") y el panel derecho solo cambia cuando hay una llamada a `write_report`. No hay que parsear texto libre ni adivinar dónde empieza el reporte.

**Regla crítica:** al refinar, `write_report` recibe el brief **completo reescrito**, nunca un fragmento. El panel se reemplaza entero; enviar solo "la sección 2 mejorada" borraría el resto.

## Contrato de la API

| Endpoint | Método | Descripción |
|---|---|---|
| `/` | GET | Sirve `index.html` |
| `/api/chat` | POST | `{session_id, message}` → `StreamingResponse` de `text/event-stream` |
| `/api/report/{session_id}` | GET | Markdown crudo del reporte actual (para el botón de descarga) |

`POST` con SSE en vez de `EventSource`, porque `EventSource` solo hace GET y mandar el mensaje en la query string obligaría a un doble round-trip. El cliente lee el stream con `fetch` + `ReadableStream` y parsea SSE a mano.

### Eventos SSE

Cada evento es una línea `data: {json}`.

| `type` | Campos | Efecto en la UI |
|---|---|---|
| `token` | `text` | Añade texto al mensaje del asistente |
| `step` | `tool`, `input` | Muestra "🔍 Buscando: *query*" |
| `step_done` | `tool`, `summary` | Cierra el paso: "✓ 5 resultados" |
| `report` | `html`, `markdown` | Reemplaza el panel derecho |
| `error` | `message` | Burbuja de error en el chat |
| `done` | — | Cierra el stream |

Mostrar los pasos importa con ReAct: cada búsqueda es visible mientras ocurre, así que una investigación que se desvía se detecta al instante en vez de al final.

**El reporte no se transmite token a token.** Llega completo en un evento `report` cuando el agente llama a `write_report`. Para un brief de una página es lo correcto: el panel pasa de "generando…" al documento terminado.

## Interfaz

Dos paneles: chat a la izquierda (~40%), brief a la derecha (~60%). El panel del brief tiene un header con el tema y un botón "Descargar .md". Estado vacío: *"Escribe un tema en el chat para generar un brief."*

`index.html`, `app.js` y `styles.css` servidos como estáticos. Sin npm, sin bundler.

**El markdown se renderiza en el servidor** con `markdown` + `bleach`, y el evento `report` lleva HTML ya sanitizado. Se prefirió esto a vendorizar `marked.js`: evita JS de terceros en el repo, y la sanitización no es opcional cuando el contenido lo redacta un LLM a partir de páginas web no controladas.

**Sesión:** `crypto.randomUUID()` en el cliente, guardado en `sessionStorage`. Si el servidor se reinició, la sesión no existe y se empieza en blanco.

**No se implementa** un indicador de cuota restante: requeriría consultar la API de OpenRouter aparte y aun así sería impreciso. En su lugar, el error 429 se reporta de forma explícita.

## Prompt de sistema

Define la calidad del reporte. Reglas:

- Rol: analista que produce briefs de 300-600 palabras en español.
- Buscar antes de afirmar. Máximo 3 búsquedas por turno.
- Citar con `[n]` y cerrar con una sección "Fuentes" con las URLs.
- Publicar **siempre** el brief con `write_report`, nunca en la respuesta del chat.
- Al refinar, reescribir el brief completo.
- Las respuestas del chat son breves y no repiten el contenido del reporte.

## Manejo de errores

| Situación | Comportamiento |
|---|---|
| Falta una clave de API | El servidor no arranca; mensaje explícito en consola |
| 429 por límite/minuto | Reintento con backoff (2s, 6s), máximo 2 veces |
| 429 por límite/día | Sin reintento. Evento `error`: "Agotaste las 50 peticiones diarias del tier gratuito. Espera al reset o cambia `MODEL_ID` a la variante de pago." |
| Fallo de Tavily | La tool devuelve el error como observación; el agente reintenta con otra query o redacta con lo que tenga |
| Se agotan las iteraciones sin `write_report` | Evento `error` explicándolo. El historial se conserva, así que el siguiente mensaje ("escribe el reporte con lo que encontraste") lo remata sin repetir la investigación |
| Markdown con HTML peligroso | `bleach` lo sanea antes de llegar al navegador |
| El cliente cierra la pestaña | El generador SSE se cancela sin dejar tareas colgadas |

`max_iterations=6` y `max_execution_time=120` acotan el peor caso a ~6 peticiones por reporte, es decir unos 8 reportes completos dentro de la cuota diaria.

## Testing

Ninguna prueba de la suite por defecto toca la red ni consume cuota.

- **`test_tools.py`** — `tavily_search` con el cliente mockeado, en éxito y en fallo; `write_report` escribe en la sesión correcta.
- **`test_agent.py`** — `FakeMessagesListChatModel` de `langchain_core` con tool calls programados. Verifica que el executor busca y después publica.
- **`test_server.py`** — `TestClient` de FastAPI con el agente mockeado. Verifica la secuencia exacta de eventos SSE y que `/api/report` devuelve el markdown.
- **Prueba de humo** marcada `@pytest.mark.live`, con claves reales, **excluida por defecto** en `pytest.ini`. Cada corrida gasta cuota real.

## Estructura de archivos

```
agente-reportes/
  app/
    __init__.py
    config.py       # variables de entorno, validación al arrancar
    llm.py          # cliente OpenRouter
    tools.py        # tavily_search + factory de write_report
    agent.py        # create_tool_calling_agent + AgentExecutor + prompt
    session.py      # store en memoria
    server.py       # FastAPI: SSE + estáticos
  static/
    index.html
    app.js
    styles.css
  tests/
    test_tools.py
    test_agent.py
    test_server.py
  .claude/agents/   # 36 subagentes de Claude Code (tooling de desarrollo)
  docs/superpowers/specs/
  .env.example      # OPENROUTER_API_KEY, TAVILY_API_KEY, MODEL_ID
  requirements.txt
  pytest.ini
  README.md
```

## Dependencias

`langchain`, `langchain-openai`, `langchain-tavily`, `fastapi`, `uvicorn`, `python-dotenv`, `markdown`, `bleach`, `pytest`, `pytest-asyncio`, `httpx`.

## Criterios de éxito

1. El usuario escribe un tema y obtiene un brief citado de 300-600 palabras en el panel derecho.
2. Las búsquedas del agente son visibles en el chat mientras ocurren.
3. Un mensaje de refinamiento actualiza el brief completo sin perder secciones.
4. El botón de descarga entrega el markdown del brief actual.
5. Agotar la cuota diaria produce un mensaje comprensible, no un error genérico.
6. La suite de tests pasa sin claves de API ni acceso a red.
