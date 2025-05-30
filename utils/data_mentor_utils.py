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

CURSOS_URL = "https://repomatic2.onrender.com/horas-por-curso"

# Definición de la función-tool para OpenAI
FUNCTION_DEF = {
    "name": "obtener_horas_por_curso",
    "description": "Devuelve un array de objetos {curso, horas} consultando /horas-por-curso",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
}

# Mensaje para el sistema
SYSTEM_PROMPT = (
    "Sos un asistente de YPF entrenado para analizar datos de encuestas y cursos otorgados "
    "por Gerentes de YPF. Cuando necesites datos de horas, invocá la función obtener_horas_por_curso."
)


def query_assistant_mentor(prompt: str, thread_id: Optional[str] = None) -> Tuple[str, str]:
    """
    Hace un chat completion con funciones:
    1) Pregunta al modelo y le permite llamar a la función automáticamente.
    2) Si el modelo invoca obtener_horas_por_curso, se hace GET real y se reinyecta la respuesta.
    3) Devuelve el texto final generado por el modelo.
    """
    # 1. Construir historial de mensajes
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]

    # 2. Llamar a la API de OpenAI, dejando que llame a la función
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=messages,
            functions=[FUNCTION_DEF],
            function_call="auto"
        )
    except Exception as e:
        # Error comunicándose con OpenAI
        err = f"Error al contactar con OpenAI: {e}"
        return err, thread_id or ""

    message = response.choices[0].message

    # 3. Si invocó la función, ejecutarla y reenviar datos
    if message.get("function_call"):
        try:
            cursos = requests.get(CURSOS_URL).json()
        except Exception as e:
            return "Error al obtener datos de cursos.", thread_id or ""

        # Agregar la llamada de función y su resultado al historial
        messages.append(message)
        messages.append({
            "role": "function",
            "name": message["function_call"]["name"],
            "content": json.dumps(cursos)
        })

        try:
            final_resp = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=messages
            )
            final_text = final_resp.choices[0].message.content
        except Exception as e:
            final_text = f"Error procesando respuesta final: {e}"
    else:
        # 4. Si no hubo llamada a función, tomar el contenido normal
        final_text = message.content or ""

    return final_text, thread_id or ""
