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
    """
    Implementá acá la lógica real que devuelva:
    { "curso1": 40, "curso2": 32, … }
    """
    # ej:
    return {
        "Python Básico": 120,
        "React Avanzado": 80,
        "Flask Deploy": 24
    }


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
    # 1) Crear o continuar el run
    if thread_id:
        url_run = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "additional_messages": [{"role": "user", "content": prompt}],
            "additional_instructions": "Responde siempre con un nuevo mensaje."
        }
    else:
        url_run = "https://api.openai.com/v1/threads/runs"
        payload = {
            "assistant_id": ASSISTANT_ID,
            "thread": {"messages": [{"role": "user", "content": prompt}]}
        }

    r = requests.post(url_run, headers=HEADERS, json=payload)
    r.raise_for_status()
    run = r.json()
    new_thread_id = run.get("thread_id") or thread_id
    run_id = run["id"]

    # 2) Poll hasta que termine
    status = run["status"]
    while status not in ("completed", "failed", "cancelled"):
        time.sleep(1)
        check = requests.get(
            f"https://api.openai.com/v1/threads/{new_thread_id}/runs/{run_id}",
            headers=HEADERS
        )
        check.raise_for_status()
        status = check.json()["status"]

    if status != "completed":
        raise RuntimeError(f"Run terminó con {status}")

    # 3) Traer mensajes
    msgs = requests.get(
        f"https://api.openai.com/v1/threads/{new_thread_id}/messages",
        headers=HEADERS
    )
    msgs.raise_for_status()
    data = msgs.json().get("data", [])

    # 4) Buscamos si el último assistant llamó a una función
    #    Asumimos que el último mensaje ROLE=assistant
    last = None
    for m in data:
        if m.get("role") == "assistant":
            last = m
    # si no hay assistant, devolvemos vacío
    if not last:
        return "", new_thread_id

    # dentro de last["content"] hay bloques con type="text" o type="function_call"
    func_block = None
    for part in last.get("content", []):
        if part.get("type") == "function_call":
            func_block = part
            break

    # 5) Si vino función, la ejecutamos y relanzamos otro run
    if func_block:
        fn_name = func_block["name"]
        args = json.loads(func_block["arguments"])

        # ejecutamos tu función real
        if fn_name in FUNCTION_MAP:
            result = FUNCTION_MAP[fn_name](**args)
        else:
            result = {"error": f"No encontré la función {fn_name}"}

        # mandamos el resultado como ROLE=function
        send_fn = requests.post(
            f"https://api.openai.com/v1/threads/{new_thread_id}/messages",
            headers=HEADERS,
            json={
                "role": "function",
                "name": fn_name,
                "content": json.dumps(result)
            }
        )
        send_fn.raise_for_status()

        # relanzamos un nuevo run SIN prompt (el assistant lo toma de tu function output)
        r2 = requests.post(
            f"https://api.openai.com/v1/threads/{new_thread_id}/runs",
            headers=HEADERS,
            json={"assistant_id": ASSISTANT_ID}
        )
        r2.raise_for_status()
        run2 = r2.json()
        run_id2 = run2["id"]
        status2 = run2["status"]

        while status2 not in ("completed", "failed", "cancelled"):
            time.sleep(1)
            c2 = requests.get(
                f"https://api.openai.com/v1/threads/{new_thread_id}/runs/{run_id2}",
                headers=HEADERS
            )
            c2.raise_for_status()
            status2 = c2.json()["status"]

        if status2 != "completed":
            raise RuntimeError(f"Segundo run terminó con {status2}")

        # volvemos a traer todos los mensajes
        final = requests.get(
            f"https://api.openai.com/v1/threads/{new_thread_id}/messages",
            headers=HEADERS
        )
        final.raise_for_status()
        data = final.json().get("data", [])

    # 6) Finalmente armamos el texto concatenado de los bloques text
    text = ""
    for m in data:
        if m.get("role") == "assistant":
            for part in m.get("content", []):
                if part.get("type") == "text":
                    text += part["text"]["value"]

    return text, new_thread_id
