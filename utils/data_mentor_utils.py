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
    """
    Igual que tu query_assistant original, pero:
    • Detecta en los mensajes si el modelo hizo un function_call de
      'obtener_horas_por_curso'
    • Si lo hizo, hace el GET a /horas-por-curso, suma las horas y devuelve
      ese texto (sin volver a llamar al modelo)
    """
    # 1) Creación o continuación de run (idéntico a tu función original)
    if thread_id:
        url = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "additional_messages": [{"role": "user", "content": prompt}],
            "additional_instructions": "Responde siempre con un nuevo mensaje."
        }
    else:
        url = "https://api.openai.com/v1/threads/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "thread": {"messages": [{"role": "user", "content": prompt}]}
        }

    resp = requests.post(url, headers=HEADERS, json=payload)
    resp.raise_for_status()
    run_data = resp.json()

    new_thread_id = run_data.get("thread_id") or thread_id
    run_id       = run_data["id"]

    # 2) Poll until completed
    status = run_data["status"]
    while status not in ["completed", "failed", "cancelled"]:
        time.sleep(1)
        check = requests.get(
            f"https://api.openai.com/v1/threads/{new_thread_id}/runs/{run_id}",
            headers=HEADERS
        )
        check.raise_for_status()
        run_data = check.json()
        status   = run_data["status"]

    if status != "completed":
        raise RuntimeError(f"Run terminó con estado '{status}'")

    # 3) Recuperar todos los mensajes del thread
    msgs = requests.get(
        f"https://api.openai.com/v1/threads/{new_thread_id}/messages",
        headers=HEADERS
    ).json().get("data", [])

    # 4) Primero: ¿el último mensaje del assistant fue un function_call?
    #    En la API de Threads, los function calls vienen como partes de content
    last = max(msgs, key=lambda m: m.get("created_at", 0))
    # Buscamos una parte de tipo function_call
    for part in last.get("content", []):
        if part.get("type") == "function_call" and part["function_call"]["name"] == "obtener_horas_por_curso":
            # Si lo pidió, hacemos el fetch directo a nuestra ruta
            cursos = requests.get("https://repomatic2.onrender.com/horas-por-curso").json()
            total  = sum(item.get("horas",0) for item in cursos)
            # Y devolvemos el texto con el total
            return f"La cantidad total de horas de los cursos es {total} horas.", new_thread_id

    # 5) Si no era un function_call, volvemos al comportamiento normal:
    #    concatenar todas las partes de tipo text
    assistant_messages = [m for m in msgs if m.get("role") == "assistant"]
    text = ""
    if assistant_messages:
        last_ass = max(assistant_messages, key=lambda m: m.get("created_at", 0))
        for part in last_ass.get("content", []):
            if part.get("type") == "text":
                text += part["text"].get("value", "")
    return text, new_thread_id
