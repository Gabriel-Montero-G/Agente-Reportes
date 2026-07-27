"""Composes the ReAct agent: prompt + tool-calling model + executor + history."""
from __future__ import annotations

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable
from langchain_core.runnables.history import RunnableWithMessageHistory

from .llm import build_llm
from .session import Session
from .tools import build_tools

MAX_ITERATIONS = 6
MAX_EXECUTION_TIME = 120

SYSTEM_PROMPT = """Eres un analista de investigación. Produces briefs de 300-600 palabras en español.

Reglas de trabajo:
1. Busca antes de afirmar. Usa `tavily_search` para verificar los hechos. Máximo 3 búsquedas por turno.
2. Publica SIEMPRE el brief llamando a la herramienta `write_report`. Nunca escribas el informe en tu respuesta de chat.
3. `write_report` recibe el informe COMPLETO en Markdown. Al refinar, reescribe el brief entero: el panel se reemplaza por completo y enviar solo un fragmento borraría el resto.
4. Estructura del brief: un título con `#`, entre 2 y 4 secciones con `##`, y una sección final `## Fuentes` con la lista numerada de URLs.
5. Cita en el cuerpo con `[n]`, donde `n` es la posición de la fuente en `## Fuentes`.
6. Tu respuesta de chat es breve (1-3 frases): di qué has hecho y qué puede pedirte a continuación. No repitas el contenido del informe.
7. Si una búsqueda falla, reformula la consulta una vez; si vuelve a fallar, escribe el brief con lo que tengas e indica la limitación.
"""


def build_agent(session: Session, llm: BaseChatModel | None = None) -> Runnable:
    """Build the agent for one session.

    Composed per session, not globally: `write_report` closes over `session`,
    so two browser tabs never write into each other's report.

    Args:
        session: the session this agent reads history from and writes reports to.
        llm: injected chat model. Tests pass a fake; production leaves it None.
    """
    tools = build_tools(session)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm or build_llm(), tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=MAX_ITERATIONS,
        max_execution_time=MAX_EXECUTION_TIME,
        handle_parsing_errors=True,
        return_intermediate_steps=False,
        verbose=False,
    )
    return RunnableWithMessageHistory(
        executor,
        lambda _session_id: session.history,
        input_messages_key="input",
        history_messages_key="chat_history",
        output_messages_key="output",
    )
