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

    # Definición de tu función-tool
    function_def = {
        "name": "obtener_horas_por_curso",
        "description": "Devuelve un array con cada curso y su cantidad de horas",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
    }

    # 1) Decidir si reuso run o creo uno nuevo
    run_data = None
    if thread_id:
        # Listar runs existentes y buscar uno activo
        list_url = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        resp_list = requests.get(list_url, headers=HEADERS)
        resp_list.raise_for_status()
        runs = resp_list.json().get("data", [])
        # Busco un run que NO esté en completed/failed/cancelled
        for r in runs:
            if r["status"] not in ["completed", "failed", "cancelled"]:
                run_data = r
                logger.info(f"4a - Reusando run activo {r['id']} con status {r['status']}")
                break

    if run_data is None:
        # No hay run activo o no había thread: creamos uno nuevo
        if thread_id:
            url = f"https://api.openai.com/v1/threads/{thread_id}/runs"
            payload = {
                "assistant_id": ASSISTANT_ID,
                "functions": [function_def],
                "function_call": "auto",
                "additional_messages": [{"role": "user", "content": prompt}]
            }
            logger.info("4b - No había run activo, creando un run nuevo en thread existente")
        else:
            url = "https://api.openai.com/v1/threads/runs"
            payload = {
                "assistant_id": ASSISTANT_ID,
                "functions": [function_def],
                "function_call": "auto",
                "thread": {"messages": [{"role": "user", "content": prompt}]}
            }
            logger.info("4c - Sin thread, creando thread y run nuevos")

        resp = requests.post(url, headers=HEADERS, json=payload)
        resp.raise_for_status()
        run_data = resp.json()

    # Extraigo IDs y estado
    new_thread_id = run_data.get("thread_id") or thread_id
    run_id        = run_data["id"]
    status        = run_data["status"]

    # 2) Polling + manejo de tool calls
    while True:
        # Si el modelo pidió tu función:
        if status == "requires_action":
            tc = run_data["required_action"]["submit_tool_outputs"]["tool_calls"][0]
            cursos = requests.get("https://repomatic2.onrender.com/horas-por-curso").json()
            submit_url = (
                f"https://api.openai.com/v1/threads/{new_thread_id}"
                f"/runs/{run_id}/tool_calls/{tc['id']}/submit"
            )
            requests.post(submit_url, headers=HEADERS, json={
                "tool_call_id": tc["id"], "output": cursos
            }).raise_for_status()
            # refresco estado
            chk = requests.get(
                f"https://api.openai.com/v1/threads/{new_thread_id}/runs/{run_id}",
                headers=HEADERS
            )
            chk.raise_for_status()
            run_data = chk.json()
            status   = run_data["status"]
            continue

        if status in ["completed", "failed", "cancelled"]:
            break

        time.sleep(1)
        chk = requests.get(
            f"https://api.openai.com/v1/threads/{new_thread_id}/runs/{run_id}",
            headers=HEADERS
        )
        chk.raise_for_status()
        run_data = chk.json()
        status   = run_data["status"]

    if status != "completed":
        raise RuntimeError(f"El run terminó con estado '{status}'.")

    # 3) Traer mensajes
    msgs = requests.get(
        f"https://api.openai.com/v1/threads/{new_thread_id}/messages",
        headers=HEADERS
    ).json().get("data", [])

    # 4) Filtrar último mensaje del assistant
    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
    text = ""
    if assistant_msgs:
        last = max(assistant_msgs, key=lambda m: m.get("created_at", 0))
        for part in last.get("content", []):
            if part.get("type") == "text":
                text += part["text"].get("value", "")

    return text, new_thread_id
