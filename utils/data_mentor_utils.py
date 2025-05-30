import os
import time
import requests
from typing import Optional, Tuple
from logging_config import logger
import json

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

import time
import requests
from typing import Optional, Tuple

# Debés tener:
# ASSISTANT_ID = "<tu_assistant_id>"
# HEADERS = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"}
# logger = tu_logger

def query_assistant_mentor(prompt: str, thread_id: Optional[str] = None) -> Tuple[str, str]:
    logger.info("3 - Entró en query_assistant_mentor")

    # 1) Definición de la función-tool que registraste en el dashboard
    function_def = {
        "name": "obtener_horas_por_curso",
        "description": "Devuelve un array de objetos {curso, horas} consultando /horas-por-curso",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    }

    # 2) Preparo el payload inicial
    if thread_id:
        # Continuar hilo
        url = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "functions": [function_def],
            "function_call": "auto",
            "additional_messages": [{"role": "user", "content": prompt}],
            "additional_instructions": "Si necesitas datos de cursos, usa la función obtener_horas_por_curso."
        }
        logger.info("4 - Continuando hilo existente")
    else:
        # Nuevo hilo
        url = "https://api.openai.com/v1/threads/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "functions": [function_def],
            "function_call": "auto",
            "thread": {"messages": [{"role": "user", "content": prompt}]}
        }
        logger.info("4 - Creando hilo nuevo")

    # 3) Llamo a OpenAI
    resp = requests.post(url, headers=HEADERS, json=payload)
    resp.raise_for_status()
    run_data = resp.json()

    new_thread = run_data.get("thread_id") or thread_id
    run_id     = run_data["id"]
    status     = run_data["status"]

    # 4) Polling + gestión de function_call
    while True:
        # Si el modelo pidió la función...
        if status == "requires_action":
            # Extraigo el call
            tc = run_data["required_action"]["submit_tool_outputs"]["tool_calls"][0]

            # Llamo a tu endpoint real
            cursos = requests.get("https://repomatic2.onrender.com/horas-por-curso").json()

            # Entrego el resultado de la función para que el run avance
            submit_url = (
                f"https://api.openai.com/v1/threads/{new_thread}"
                f"/runs/{run_id}/tool_calls/{tc['id']}/submit"
            )
            requests.post(
                submit_url,
                headers=HEADERS,
                json={"tool_call_id": tc["id"], "output": cursos}
            ).raise_for_status()

            # Actualizo estado y sigo
            check = requests.get(
                f"https://api.openai.com/v1/threads/{new_thread}/runs/{run_id}",
                headers=HEADERS
            )
            check.raise_for_status()
            run_data = check.json()
            status   = run_data["status"]
            continue

        # Si ya terminó...
        if status in ["completed", "failed", "cancelled"]:
            break

        # Si sigue en curso, espero y refresco
        time.sleep(1)
        check = requests.get(
            f"https://api.openai.com/v1/threads/{new_thread}/runs/{run_id}",
            headers=HEADERS
        )
        check.raise_for_status()
        run_data = check.json()
        status   = run_data["status"]

    if status != "completed":
        raise RuntimeError(f"Run terminó en estado '{status}'")

    # 5) Obtengo todos los mensajes del assistant
    msgs = requests.get(
        f"https://api.openai.com/v1/threads/{new_thread}/messages",
        headers=HEADERS
    ).json().get("data", [])

    # 6) Busco la respuesta final del assistant (texto)
    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
    final_text = ""
    if assistant_msgs:
        last = max(assistant_msgs, key=lambda m: m.get("created_at", 0))
        for part in last.get("content", []):
            if part.get("type") == "text":
                final_text += part["text"].get("value", "")

    return final_text, new_thread