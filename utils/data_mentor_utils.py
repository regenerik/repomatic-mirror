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

# Definición de la función-tool para OpenAI
FUNCTION_DEF = {
    "name": "obtener_horas_por_curso",
    "description": "Devuelve un array de objetos {curso, horas} consultando /horas-por-curso",  
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
}

# URL de tu endpoint de cursos
CURSOS_URL = "https://repomatic2.onrender.com/horas-por-curso"

# System prompt para el asistente
SYSTEM_PROMPT = (
    "Sos un asistente de YPF entrenado para analizar datos de encuestas y cursos otorgados "
    "por Gerentes de YPF. Para requests de horas, llamá a la función obtener_horas_por_curso."
)

def query_assistant_mentor(prompt: str, thread_id: Optional[str] = None) -> Tuple[str, str]:
    """
    Usa la API de chat completions con OpenAI Functions:
    1. Envia el mensaje y permite function_call automatico.
    2. Si el modelo llama a obtener_horas_por_curso, hacemos GET a tu endpoint real.
    3. Alimentamos la respuesta de la función y devolvemos la respuesta final.
    """
    # Construir historial de mensajes
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]

    # 1) Primera llamada: pedir al modelo, dejando que llame a la función
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=messages,
        functions=[FUNCTION_DEF],
        function_call="auto"
    )
    message = response.choices[0].message

    # 2) Si llamó a nuestra función, ejecutarla y volver a llamar para la respuesta final
    if message.get("function_call"):
        # Hacer GET real
        cursos = requests.get(CURSOS_URL).json()
        # Agregar la función como mensaje
        messages.append(message)
        messages.append({
            "role": "function",
            "name": message["function_call"]["name"],
            "content": openai.util.to_json(cursos)
        })
        final_resp = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=messages
        )
        final_text = final_resp.choices[0].message.content
    else:
        # No hubo function_call, usar el contenido normal
        final_text = message.content

    # thread_id no se usa en este enfoque, devolvemos el incoming o None
    return final_text, thread_id or ""
