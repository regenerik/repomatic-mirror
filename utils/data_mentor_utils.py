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
    """
    Envía un prompt al asistente con ID ASSISTANT_ID utilizando la API de OpenAI.
    - Si NO hay thread_id => se crea un nuevo hilo (POST /v1/threads/runs).
    - Si SÍ hay thread_id => se continúa el hilo existente (POST /v1/threads/{thread_id}/runs).

    Gestiona llamadas a funciones (tool calls) y polling hasta completion.
    """

    full_prompt = prompt

    # 4) Preparar URL y payload según exista hilo o no
    if thread_id:
        logger.info("4 - Ya hay hilo.. siguiendo por esa lógica...")
        create_run_url = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "additional_messages": [
                {"role": "user", "content": full_prompt}
            ],
            "additional_instructions": "Responde siempre con un nuevo mensaje."
        }
    else:
        logger.info("4 - No hay hilo.. creando hilo nuevo...")
        create_run_url = "https://api.openai.com/v1/threads/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "thread": {"messages": [{"role": "user", "content": full_prompt}]}
        }

    logger.info("5 - Por hacer la llamada a openai...")
    # 1) Crear o continuar el run
    try:
        response = requests.post(create_run_url, headers=HEADERS, json=payload)
        response.raise_for_status()
    except Exception as e:
        logger.error("Error llamando a OpenAI: %s — body: %s", e, response.text if 'response' in locals() else "")
        raise
    
    run_data = response.json()

    # Obtener thread_id y run_id
    new_thread_id = run_data.get("thread_id") or thread_id
    run_id = run_data["id"]
    run_status = run_data.get("status")

    # 2) Polling y gestión de tool calls
    while True:
        # 2.1) Si el modelo pidió una función, ejecutarla y enviarla
        if run_status == "requires_action":
            tc = run_data["required_action"]["submit_tool_outputs"]["tool_calls"][0]
            # Llamar a tu API Flask real
            cursos = requests.get(
                "https://repomatic2.onrender.com/horas-por-curso"
            ).json()
            # Enviar el output a OpenAI para completar el run
            submit_url = (
                f"https://api.openai.com/v1/threads/{new_thread_id}"
                f"/runs/{run_id}/tool_calls/{tc['id']}/submit"
            )
            requests.post(
                submit_url,
                headers=HEADERS,
                json={"tool_call_id": tc["id"], "output": cursos}
            ).raise_for_status()
            # Volver a pedir el estado actualizado
            get_run = requests.get(
                f"https://api.openai.com/v1/threads/{new_thread_id}/runs/{run_id}",
                headers=HEADERS
            )
            get_run.raise_for_status()
            run_data = get_run.json()
            run_status = run_data.get("status")
            continue

        # 2.2) Si el run terminó, salimos
        if run_status in ["completed", "failed", "cancelled"]:
            break

        # 2.3) Si sigue corriendo, esperamos y refrescamos
        time.sleep(1)
        get_run = requests.get(
            f"https://api.openai.com/v1/threads/{new_thread_id}/runs/{run_id}",
            headers=HEADERS
        )
        get_run.raise_for_status()
        run_data = get_run.json()
        run_status = run_data.get("status")

    if run_status != "completed":
        raise RuntimeError(f"El run terminó con estado '{run_status}' y no se completó correctamente.")

    # 3) Recuperar mensajes del thread
    messages_url = f"https://api.openai.com/v1/threads/{new_thread_id}/messages"
    messages_response = requests.get(messages_url, headers=HEADERS)
    messages_response.raise_for_status()
    messages_data = messages_response.json()

    # 4) Filtrar y concatenar texto del último mensaje de assistant
    assistant_messages = [
        msg for msg in messages_data.get("data", []) if msg.get("role") == "assistant"
    ]
    assistant_message = ""
    if assistant_messages:
        last_msg = max(assistant_messages, key=lambda m: m.get("created_at", 0))
        for part in last_msg.get("content", []):
            if part.get("type") == "text":
                assistant_message += part.get("text", {}).get("value", "")

    return assistant_message, new_thread_id
