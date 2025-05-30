import os
import requests
from typing import Optional, Tuple
from logging_config import logger
import json
from openai import OpenAI
client = OpenAI()

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


CURSOS_URL = "https://repomatic2.onrender.com/horas-por-curso"

# Definición de la función para function calling
TOOL_DEF = {
    "type": "function",
    "name": "obtener_horas_por_curso",
    "description": "Devuelve lista de cursos con sus horas consultando /horas-por-curso",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    "strict": True
}

# Mensaje de sistema
SYSTEM_PROMPT = (
    "Sos un asistente de YPF entrenado para analizar datos de encuestas y cursos otorgados "
    "por Gerentes de YPF. Cuando necesites datos de horas, invocá la función obtener_horas_por_curso."
)

def query_assistant_mentor(prompt: str, thread_id: Optional[str] = None) -> Tuple[str, str]:
    """
    Usa la API Responses de openai-python >=1.0.0 con función `obtener_horas_por_curso`:
      1) Llama a client.responses.create con input=mensajes y tools=[TOOL_DEF]
      2) Si el modelo decide hacer function_call: ejecuta GET real a CURSOS_URL
      3) Vuelve a llamar a client.responses.create incluyendo output de la función
      4) Devuelve final.output_text como respuesta
    """
    # 1) Armar input para Responses API
    input_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt}
    ]

    # 2) Primera llamada: modelo puede decidir usar la función
    try:
        initial = client.responses.create(
            model="gpt-4o",
            input=input_messages,
            tools=[TOOL_DEF]
        )
    except Exception as e:
        return f"Error comunicándose con OpenAI: {e}", thread_id or ""

    # Filtrar llamadas a función
    tool_calls = [item for item in initial.output if item.get("type") == "function_call"]

    # 3) Si hay llamada a obtener_horas_por_curso
    if tool_calls:
        call = tool_calls[0]
        # Ejecutar en tu servidor
        try:
            cursos = requests.get(CURSOS_URL).json()
        except Exception:
            return "Error al obtener datos de cursos.", thread_id or ""

        # 4) Rearmar input con la respuesta de la función
        input_messages.append({
            "type": "function_call",
            "name": call["name"],
            "arguments": call.get("arguments", "{}")
        })
        input_messages.append({
            "type": "function_call_output",
            "call_id": call.get("call_id", ""),
            "output": json.dumps(cursos)
        })

        # 5) Segunda llamada para respuesta final
        try:
            final = client.responses.create(
                model="gpt-4o",
                input=input_messages,
                tools=[TOOL_DEF]
            )
            return final.output_text, thread_id or ""
        except Exception as e:
            return f"Error generando respuesta final: {e}", thread_id or ""

    # 6) Si no llamó a función, devolvemos el texto generado
    return initial.output_text, thread_id or ""
