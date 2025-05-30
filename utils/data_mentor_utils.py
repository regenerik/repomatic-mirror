import os
import requests
from typing import Optional, Tuple
from logging_config import logger
import json
from openai import OpenAI
client = OpenAI()

# Asegurate de tener definida la variable de entorno OPENAI_API_KEY
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Debes definir la variable de entorno OPENAI_API_KEY con tu clave de API.")

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "OpenAI-Beta": "assistants=v2"
}

ASSISTANT_ID = "asst_Gy0OKzAqKGqXiU25q9Z89Ifs"


CURSOS_URL = "https://repomatic2.onrender.com/horas-por-curso"

# Definición de la función para function calling
TOOL_DEF = {
    "type": "function",
    "name": "obtener_horas_por_curso",
    "description": "Devuelve lista de cursos con sus horas consultando /horas-por-curso",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    "strict": True
}

# Mensaje de sistema
SYSTEM_PROMPT = (
    "Sos un asistente de YPF entrenado para analizar datos de encuestas y cursos otorgados "
    "por Gerentes de YPF. Cuando necesites datos de horas, invocá la función obtener_horas_por_curso."
)

client = OpenAI()


def query_assistant_mentor(
    prompt: str,
    thread_id: str | None = None
) -> tuple[list[dict], str]:
    """
    Le pasa tu prompt al Assistant configurado en el dashboard, maneja hilos
    y devuelve TODO lo que salió (texto, function_call, etc.) + el thread_id.

    Args:
      - prompt: el mensaje del usuario.
      - thread_id: si ya tenés un hilo previo, pasalo para seguir el contexto.

    Returns:
      - messages: lista de mensajes del thread (cada uno con role/content o function_call).  
      - thread_id: el ID del thread (novedad o el mismo que pasaste).
    """
    # 1) Crear hilo si hace falta
    if not thread_id:
        thread = client.beta.threads.create()  # :contentReference[oaicite:0]{index=0}
        thread_id = thread.id

    # 2) Mandar tu mensaje al thread
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=prompt,
    )  # :contentReference[oaicite:1]{index=1}

    # 3) Ejecutar el run (el Assistant se activa y usa sus funciones si las necesita)
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
    )  # :contentReference[oaicite:2]{index=2}

    # 4) Esperar a que termine
    status = run.status
    while status in ("queued", "in_progress"):
        time.sleep(0.5)
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id,
        )  # :contentReference[oaicite:3]{index=3}
        status = run.status

    if status != "completed":
        raise RuntimeError(f"El Run terminó con estado '{status}'.")

    # 5) Recuperar todos los mensajes del thread (texto y function_calls)
    resp = client.beta.threads.messages.list(
        thread_id=thread_id,
        order="asc",
    )  # :contentReference[oaicite:4]{index=4}

    return resp.data, thread_id