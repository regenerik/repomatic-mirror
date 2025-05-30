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
#  TUS FUNCIONES LOCALES (idénticas a las del dashboard)
# ——————————————————————————————————————————
def obtener_horas_por_curso() -> dict:
    logger.info("Entré a obtener_horas_por_curso()")
    # ejemplo de resultado
    result = {
        "Python Básico": 120,
        "React Avanzado": 80,
        "Flask Deploy": 24
    }
    logger.info(f"Resultado de obtener_horas_por_curso: {result}")
    return result


FUNCTION_MAP = {
    "obtener_horas_por_curso": obtener_horas_por_curso,
    # agregá más mapeos si tenés otras funciones
}


# ——————————————————————————————————————————
#  UTIL PRINCIPAL
# ——————————————————————————————————————————
def query_assistant_mentor(
    prompt: str,
    thread_id: Optional[str] = None
) -> Tuple[str, str]:
    """
    Le manda `prompt` al assistant. Si viene función, la ejecuta y vuelve a correr el run.
    Devuelve (respuesta_de_texto, thread_id).
    """
    logger.info(f"query_assistant_mentor arrancó con prompt={prompt!r}, thread_id={thread_id!r}")

    # 1) Crear o continuar el run
    if thread_id:
        url_run = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "additional_messages": [{"role": "user", "content": prompt}],
            "additional_instructions": "Responde siempre con un nuevo mensaje."
        }
        logger.info(f"Continuando run existente: {url_run} payload={payload}")
    else:
        url_run = "https://api.openai.com/v1/threads/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "thread": {"messages": [{"role": "user", "content": prompt}]}
        }
        logger.info(f"Iniciando run nuevo: {url_run} payload={payload}")

    r = requests.post(url_run, headers=HEADERS, json=payload)
    logger.info(f"POST run -> status_code={r.status_code}")
    r.raise_for_status()
    run = r.json()
    new_thread_id = run.get("thread_id") or thread_id
    run_id = run["id"]
    logger.info(f"Run creado/id obtenido: thread_id={new_thread_id}, run_id={run_id}")

    # 2) Poll hasta que termine
    status = run["status"]
    logger.info(f"Estado inicial del run: {status}")
    while status not in ("completed", "failed", "cancelled"):
        time.sleep(1)
        logger.info("Esperando completion, chequeando nuevamente...")
        check = requests.get(
            f"https://api.openai.com/v1/threads/{new_thread_id}/runs/{run_id}",
            headers=HEADERS
        )
        logger.info(f"GET run status -> status_code={check.status_code}")
        check.raise_for_status()
        status = check.json()["status"]
        logger.info(f"Estado del run tras polling: {status}")

    if status != "completed":
        logger.error(f"Run terminó con estado no exitoso: {status}")
        raise RuntimeError(f"Run terminó con {status}")
    logger.info("Run completado correctamente")

    # 3) Traer mensajes
    logger.info("Recuperando mensajes del thread")
    msgs = requests.get(
        f"https://api.openai.com/v1/threads/{new_thread_id}/messages",
        headers=HEADERS
    )
    logger.info(f"GET messages -> status_code={msgs.status_code}")
    msgs.raise_for_status()
    data = msgs.json().get("data", [])
    logger.info(f"Mensajes recibidos: {len(data)} items")

    # 4) Buscamos si el último assistant llamó a una función
    last = None
    for m in data:
        if m.get("role") == "assistant":
            last = m
    logger.info(f"Último mensaje de assistant: {last!r}")
    if not last:
        logger.info("No encontré mensaje de assistant, devolviendo vacío")
        return "", new_thread_id

    func_block = None
    for part in last.get("content", []):
        if part.get("type") == "function_call":
            func_block = part
            break
    logger.info(f"Bloque de function_call detectado: {func_block!r}")

    # 5) Si vino función, la ejecutamos y relanzamos otro run
    if func_block:
        fn_name = func_block["name"]
        args = json.loads(func_block["arguments"])
        logger.info(f"Ejecutando función local {fn_name} con args {args}")

        if fn_name in FUNCTION_MAP:
            result = FUNCTION_MAP[fn_name](**args)
        else:
            result = {"error": f"No encontré la función {fn_name}"}
        logger.info(f"Resultado de la función {fn_name}: {result}")

        # mandamos el resultado como ROLE=function
        logger.info("Enviando output de la función al thread")
        send_fn = requests.post(
            f"https://api.openai.com/v1/threads/{new_thread_id}/messages",
            headers=HEADERS,
            json={
                "role": "function",
                "name": fn_name,
                "content": json.dumps(result)
            }
        )
        logger.info(f"POST function output -> status_code={send_fn.status_code}")
        send_fn.raise_for_status()

        # relanzamos un nuevo run SIN prompt
        logger.info("Relanzando segundo run sin prompt")
        r2 = requests.post(
            f"https://api.openai.com/v1/threads/{new_thread_id}/runs",
            headers=HEADERS,
            json={"assistant_id": ASSISTANT_ID}
        )
        logger.info(f"POST second run -> status_code={r2.status_code}")
        r2.raise_for_status()
        run2 = r2.json()
        run_id2 = run2["id"]
        status2 = run2["status"]
        logger.info(f"Segundo run creado: run_id={run_id2}, estado inicial={status2}")

        while status2 not in ("completed", "failed", "cancelled"):
            time.sleep(1)
            logger.info("Esperando completion del segundo run...")
            c2 = requests.get(
                f"https://api.openai.com/v1/threads/{new_thread_id}/runs/{run_id2}",
                headers=HEADERS
            )
            logger.info(f"GET second run status -> status_code={c2.status_code}")
            c2.raise_for_status()
            status2 = c2.json()["status"]
            logger.info(f"Estado segundo run tras polling: {status2}")

        if status2 != "completed":
            logger.error(f"Segundo run terminó con estado no exitoso: {status2}")
            raise RuntimeError(f"Segundo run terminó con {status2}")
        logger.info("Segundo run completado correctamente")

        # volvemos a traer todos los mensajes
        logger.info("Recuperando mensajes finales del thread")
        final = requests.get(
            f"https://api.openai.com/v1/threads/{new_thread_id}/messages",
            headers=HEADERS
        )
        logger.info(f"GET final messages -> status_code={final.status_code}")
        final.raise_for_status()
        data = final.json().get("data", [])
        logger.info(f"Mensajes finales recibidos: {len(data)} items")

    # 6) Finalmente armamos el texto concatenado de los bloques text
    text = ""
    for m in data:
        if m.get("role") == "assistant":
            for part in m.get("content", []):
                if part.get("type") == "text":
                    text += part["text"]["value"]
    logger.info(f"Texto final devuelto: {text!r}")

    return text, new_thread_id
