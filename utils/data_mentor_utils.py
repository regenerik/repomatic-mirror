import os
import time
import requests
from typing import Optional, Tuple
from logging_config import logger
import json
import openai

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

# Definición de la herramienta para function calling (se usa en 'tools')
TOOL_DEF = {
    "type": "function",
    "name": "obtener_horas_por_curso",
    "description": "Llama al endpoint /horas-por-curso y devuelve lista de cursos con sus horas",
    "parameters": {
        "type": "object",
        "properties": {},
        "additionalProperties": False
    },
    "strict": True
}

SYSTEM_PROMPT = (
    "Sos un asistente de YPF entrenado para analizar datos de encuestas y cursos otorgados "
    "por Gerentes de YPF. Cuando necesites datos de horas, utilizá la función obtener_horas_por_curso."
)

def query_assistant_mentor(prompt: str, thread_id: Optional[str] = None) -> Tuple[str, str]:
    """
    Usa la API Responses de openai-python >=1.0.0 con function calling:
      1) Llama a client.responses.create con tools=[TOOL_DEF]
      2) Si el modelo decide hacer un function_call, ejecuta GET real a CURSOS_URL
      3) Reimplementa otra llamada a responses.create con el resultado de la función
      4) Devuelve el texto final generado por el modelo
    """
    # 1) Construir el input inicial: mensajes de sistema + usuario
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt}
    ]

    # 2) Llamada inicial: el modelo puede invocar la función
    try:
        initial = client.responses.create(
            model="gpt-4o",
            input=messages,
            tools=[TOOL_DEF]
        )
    except Exception as e:
        # Algo salió mal con la API
        err = f"Error comunicándose con OpenAI: {e}"
        return err, thread_id or ""

    # 'initial.output' es la lista de items (puede haber function_call)
    tool_calls = [item for item in initial.output if item["type"] == "function_call"]

    if tool_calls:
        # Tomamos el primer function_call que pidió el modelo
        call = tool_calls[0]
        try:
            cursos = requests.get(CURSOS_URL).json()
        except Exception:
            return "Error al obtener datos de cursos.", thread_id or ""

        # 3) Preparamos el nuevo input: mensajes + función + resultado
        messages.append({
            "type": "function_call",  # model's function request
            "name": call["name"],
            "arguments": call["arguments"]
        })
        messages.append({
            "type": "function_call_output",
            "call_id": call["call_id"],
            "output": json.dumps(cursos)
        })

        # 4) Segunda llamada: el modelo integra el resultado
        try:
            final = client.responses.create(
                model="gpt-4o",
                input=messages,
                tools=[TOOL_DEF]
            )
            # El texto final está en .output_text
            text = final.output_text
        except Exception as e:
            text = f"Error generando la respuesta final: {e}"
    else:
        # Sin function_call: tomamos el output directo como texto
        text = initial.output_text

    return text, thread_id or ""
