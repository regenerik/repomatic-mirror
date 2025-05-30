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

    # 1) Crear o continuar el run en Threads API SIN functions ni function_call en payload
    if thread_id:
        url = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "additional_messages": [{"role": "user", "content": prompt}],
            "additional_instructions": "Responde siempre con un nuevo mensaje."
        }
        logger.info("4 - Continuando hilo existente")
    else:
        url = "https://api.openai.com/v1/threads/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "thread": {"messages": [{"role": "user", "content": prompt}]}            
        }
        logger.info("4 - Creando hilo nuevo")

    # 2) Invocar la API de Threads
    resp = requests.post(url, headers=HEADERS, json=payload)
    resp.raise_for_status()
    run_data = resp.json()

    # 3) Extraer thread_id, run_id y estado
    new_thread_id = run_data.get("thread_id") or thread_id
    run_id        = run_data["id"]
    status        = run_data.get("status")

    # 4) Polling + manejo de requires_action para llamar a tu función real
    while True:
        if status == "requires_action":
            # Extraer el tool_call
            tc = run_data["required_action"]["submit_tool_outputs"]["tool_calls"][0]
            # Llamar a tu endpoint real de cursos
            cursos = requests.get("https://repomatic2.onrender.com/horas-por-curso").json()
            # Enviar el resultado de la función para que el run prosiga
            submit_url = (
                f"https://api.openai.com/v1/threads/{new_thread_id}"
                f"/runs/{run_id}/tool_calls/{tc['id']}/submit"
            )
            requests.post(
                submit_url,
                headers=HEADERS,
                json={"tool_call_id": tc["id"], "output": cursos}
            ).raise_for_status()
            # Actualizar estado
            run_data = requests.get(
                f"https://api.openai.com/v1/threads/{new_thread_id}/runs/{run_id}",
                headers=HEADERS
            ).json()
            status = run_data.get("status")
            continue

        if status in ["completed", "failed", "cancelled"]:
            break

        time.sleep(1)
        run_data = requests.get(
            f"https://api.openai.com/v1/threads/{new_thread_id}/runs/{run_id}",
            headers=HEADERS
        ).json()
        status   = run_data.get("status")

    if status != "completed":
        raise RuntimeError(f"Run terminó con estado '{status}'")

    # 5) Recuperar mensajes del thread
    messages = requests.get(
        f"https://api.openai.com/v1/threads/{new_thread_id}/messages",
        headers=HEADERS
    ).json().get("data", [])

    # 6) Filtrar y concatenar la última respuesta del assistant
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    result_text = ""
    if assistant_msgs:
        last = max(assistant_msgs, key=lambda m: m.get("created_at", 0))
        for part in last.get("content", []):
            if part.get("type") == "text":
                result_text += part["text"].get("value", "")

    return result_text, new_thread_id