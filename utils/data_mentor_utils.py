import os
import time
import requests
import json
from typing import Optional, Tuple
from logging_config import logger

# ——————————————————————————————————————————
#  CONFIG
# ——————————————————————————————————————————
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Tenés que definir OPENAI_API_KEY en tus env vars")

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "OpenAI-Beta": "assistants=v2"
}

ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID", "asst_Gy0OKzAqKGqXiU25q9Z89Ifs")


# ——————————————————————————————————————————
#  TUS FUNCIONES LOCALES
# ——————————————————————————————————————————
def obtener_horas_por_curso() -> dict:
    logger.info("Entré a obtener_horas_por_curso()")
    result = {
        "Python Básico": 120,
        "React Avanzado": 80,
        "Flask Deploy": 24
    }
    logger.info(f"Resultado de obtener_horas_por_curso: {result}")
    return result


FUNCTION_MAP = {
    "obtener_horas_por_curso": obtener_horas_por_curso,
}


# ——————————————————————————————————————————
#  UTIL PRINCIPAL
# ——————————————————————————————————————————
def query_assistant_mentor(
    prompt: str,
    thread_id: Optional[str] = None
) -> Tuple[str, str]:
    logger.info(f"query_assistant_mentor arrancó con prompt={prompt!r}, thread_id={thread_id!r}")

    # 1) Crear o continuar el run
    if thread_id:
        url_run = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "additional_messages": [{"role": "user", "content": prompt}],
            "additional_instructions": "Responde siempre con un nuevo mensaje."
        }
        logger.info(f"Continuando run existente: {url_run}")
    else:
        url_run = "https://api.openai.com/v1/threads/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "thread": {"messages": [{"role": "user", "content": prompt}]}
        }
        logger.info(f"Iniciando run nuevo: {url_run}")

    r = requests.post(url_run, headers=HEADERS, json=payload)
    r.raise_for_status()
    run = r.json()
    new_thread_id = run.get("thread_id") or thread_id
    run_id = run["id"]
    logger.info(f"Run enviado: thread_id={new_thread_id}, run_id={run_id}")

    # 2) Poll hasta que termine o requiera acción (function_call)
    status = run["status"]
    logger.info(f"Estado inicial del run: {status}")
    while status not in ("completed", "failed", "cancelled", "requires_action"):
        time.sleep(1)
        logger.info("Polling…")
        check = requests.get(
            f"https://api.openai.com/v1/threads/{new_thread_id}/runs/{run_id}",
            headers=HEADERS
        )
        check.raise_for_status()
        status = check.json()["status"]
        logger.info(f"Estado tras polling: {status}")

    if status == "failed" or status == "cancelled":
        logger.error(f"Run terminó mal con estado: {status}")
        raise RuntimeError(f"Run terminó con {status}")
    logger.info(f"Polling salió con estado: {status}")

    # 3) Recibir mensajes
    msgs = requests.get(
        f"https://api.openai.com/v1/threads/{new_thread_id}/messages",
        headers=HEADERS
    )
    msgs.raise_for_status()
    data = msgs.json().get("data", [])
    logger.info(f"Recibí {len(data)} mensajes en el thread")

    # 4) Buscar un bloque function_call en el último assistant
    last_assistant = None
    for m in data:
        if m.get("role") == "assistant":
            last_assistant = m
    logger.info(f"Último mensaje assistant: {last_assistant}")

    func_block = None
    if last_assistant:
        for part in last_assistant.get("content", []):
            if part.get("type") == "function_call":
                func_block = part
                break
    logger.info(f"Bloque function_call: {func_block}")

    # 5) Si hay function_call ejecutarlo y relanzar run
    if func_block:
        fn_name = func_block["name"]
        args = json.loads(func_block["arguments"])
        logger.info(f"Ejecutando función {fn_name} con args {args}")

        result = FUNCTION_MAP.get(fn_name, lambda **k: {"error": f"No encontré {fn_name}"})(**args)
        logger.info(f"Resultado función: {result}")

        # enviar resultado de la función
        post_fn = requests.post(
            f"https://api.openai.com/v1/threads/{new_thread_id}/messages",
            headers=HEADERS,
            json={"role": "function", "name": fn_name, "content": json.dumps(result)}
        )
        post_fn.raise_for_status()
        logger.info("Resultado de función enviado")

        # relanzar run sin prompt
        r2 = requests.post(
            f"https://api.openai.com/v1/threads/{new_thread_id}/runs",
            headers=HEADERS,
            json={"assistant_id": ASSISTANT_ID}
        )
        r2.raise_for_status()
        run2 = r2.json()
        run_id2 = run2["id"]
        status2 = run2["status"]
        logger.info(f"Segundo run: run_id={run_id2}, estado={status2}")

        while status2 not in ("completed", "failed", "cancelled"):
            time.sleep(1)
            c2 = requests.get(
                f"https://api.openai.com/v1/threads/{new_thread_id}/runs/{run_id2}",
                headers=HEADERS
            )
            c2.raise_for_status()
            status2 = c2.json()["status"]
            logger.info(f"Polling segundo run: estado={status2}")

        if status2 != "completed":
            logger.error(f"Segundo run mal: {status2}")
            raise RuntimeError(f"Segundo run terminó con {status2}")
        logger.info("Segundo run completado")

        # recargamos mensajes finales
        final = requests.get(
            f"https://api.openai.com/v1/threads/{new_thread_id}/messages",
            headers=HEADERS
        )
        final.raise_for_status()
        data = final.json().get("data", [])
        logger.info(f"Mensajes finales recibidos: {len(data)}")

    # 6) Armamos el texto
    text = ""
    for m in data:
        if m.get("role") == "assistant":
            for part in m.get("content", []):
                if part.get("type") == "text":
                    text += part["text"]["value"]

    logger.info(f"Texto final: {text!r}")
    return text, new_thread_id
