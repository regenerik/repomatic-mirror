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

def query_assistant_mentor(prompt: str, thread_id: Optional[str] = None) -> Tuple[str, str]:
    logger.info("3 - Entró en el útil query_assistant_mentor...")
    
    # Configuración de la función que va a llamar el modelo
    function_def = {
      "name": "obtener_horas_por_curso",
      "description": "Devuelve un array con cada curso y su cantidad de horas",
      "parameters": {
        "type": "object",
        "properties": {},
        "additionalProperties": False
      }
    }

    # 1) Elegir URL y payload inicial
    if thread_id:
        logger.info("4 - Ya hay hilo, continuamos el run existente")
        url = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "functions": [function_def],
            "function_call": "auto",
            "additional_messages": [{"role": "user", "content": prompt}],
            "additional_instructions": "Responde siempre con un nuevo mensaje."
        }
    else:
        logger.info("4 - No hay hilo, creamos uno nuevo")
        url = "https://api.openai.com/v1/threads/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "functions": [function_def],
            "function_call": "auto",
            "thread": {"messages": [{"role": "user", "content": prompt}]}
        }

    logger.info("5 - Llamando a OpenAI para crear/continuar run")
    resp = requests.post(url, headers=HEADERS, json=payload)
    resp.raise_for_status()
    run_data = resp.json()

    new_thread = run_data.get("thread_id") or thread_id
    run_id     = run_data["id"]
    status     = run_data["status"]

    # 2) Polling y manejo de llamadas a la función
    while True:
        # Si el modelo solicitó la función...
        if status == "requires_action":
            tc = run_data["required_action"]["submit_tool_outputs"]["tool_calls"][0]
            # Ejecutamos la llamada real
            cursos = requests.get(
                "https://repomatic2.onrender.com/horas-por-curso"
            ).json()
            # Enviamos el resultado para que el run avance
            submit_url = (
                f"https://api.openai.com/v1/threads/{new_thread}"
                f"/runs/{run_id}/tool_calls/{tc['id']}/submit"
            )
            requests.post(
                submit_url,
                headers=HEADERS,
                json={"tool_call_id": tc["id"], "output": cursos}
            ).raise_for_status()
            # Actualizamos estado
            check = requests.get(
                f"https://api.openai.com/v1/threads/{new_thread}/runs/{run_id}",
                headers=HEADERS
            )
            check.raise_for_status()
            run_data = check.json()
            status   = run_data["status"]
            continue

        # Si terminó (completado, falló o cancelado), salimos
        if status in ["completed", "failed", "cancelled"]:
            break

        # Si sigue corriendo, esperamos un segundo y refrescamos
        time.sleep(1)
        check = requests.get(
            f"https://api.openai.com/v1/threads/{new_thread}/runs/{run_id}",
            headers=HEADERS
        )
        check.raise_for_status()
        run_data = check.json()
        status   = run_data["status"]

    if status != "completed":
        raise RuntimeError(f"Run terminó con estado '{status}'")

    # 3) Una vez completado, traemos mensajes
    msgs = requests.get(
        f"https://api.openai.com/v1/threads/{new_thread}/messages",
        headers=HEADERS
    ).json().get("data", [])

    # 4) Filtramos el último assistant message y concatenamos texto
    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
    result = ""
    if assistant_msgs:
        last = max(assistant_msgs, key=lambda m: m.get("created_at", 0))
        for part in last.get("content", []):
            if part.get("type") == "text":
                result += part["text"].get("value", "")

    return result, new_thread