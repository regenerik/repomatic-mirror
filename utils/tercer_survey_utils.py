from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from io import BytesIO
from database import db
from models import TercerSurvey
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from io import BytesIO
import pytz
from dotenv import load_dotenv
load_dotenv()
import os
from logging_config import logger
import gc
from datetime import datetime
import time
import random
# Zona horaria de São Paulo/Buenos Aires
tz = pytz.timezone('America/Sao_Paulo')

# - Creando cliente openai
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    organization="org-cSBk1UaTQMh16D7Xd9wjRUYq"
)


#----------------UTILS PARA TERCER SURVEY------------------------///////////////////////

def get_with_retries(url, headers, max_retries=5, backoff_base=1.5, page=None):
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=20)
        except Exception as e:
            logger.error(f"Excepción request página {page}: {e}")
            time.sleep(2)
            continue

        if resp.status_code == 200:
            logger.info(f"Página {page}: OK (status 200)")
            return resp
        elif resp.status_code == 429:
            wait = backoff_base * (2 ** attempt) + random.uniform(0,1)
            logger.warning(f"Pág {page}: Rate limited (429). Reintentando en {wait:.2f}s (intento {attempt+1}/{max_retries})")
            time.sleep(wait)
        else:
            logger.error(f"Pág {page}: Error inesperado {resp.status_code}")
            break
    logger.error(f"Página {page}: No se pudo recuperar luego de {max_retries} intentos.")
    return resp  # devolver última respuesta (429 o error) para manejar abort

def obtener_y_guardar_survey():
    api_key = os.getenv('SURVEYMONKEY_API_KEY')
    access_token = os.getenv('SURVEYMONKEY_ACCESS_TOKEN')
    survey_id = '416779463'
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    HOST = "https://api.surveymonkey.com"
    ENDPOINT = f"/v3/surveys/{survey_id}/responses/bulk"
    hora_inicio = datetime.now()
    logger.info("Arrancando tercer survey...")

    # Primera página para leer total y per_page
    url1 = f"{HOST}{ENDPOINT}?page=1&per_page=1000"
    resp1 = get_with_retries(url1, headers, page=1)
    if resp1 is None or resp1.status_code != 200:
        logger.error("No se pudo recuperar la primera página. Abortando.")
        return
    body1 = resp1.json()
    per_page = body1.get("per_page", len(body1.get("data", [])))
    total = body1.get("total", None)
    total_pages = None
    # Si SurveyMonkey devuelve headers con total_pages:
    if 'X-Total-Pages' in resp1.headers:
        total_pages = int(resp1.headers['X-Total-Pages'])
    elif total and per_page:
        total_pages = (total + per_page - 1) // per_page
    else:
        # fallback si no hay total: usamos links.next
        total_pages = 1
        tmp = body1.get("links", {})
        while tmp.get("next"):
            total_pages += 1
            tmp = {}  # no paginar más en esta lógica simple

    logger.info(f"Total respuestas estimadas: {total}, por página: {per_page}, total_pages: {total_pages}")

    all_results = body1.get("data", [])
    # bajar páginas 2...total_pages
    for page in range(2, total_pages+1):
        u = f"{HOST}{ENDPOINT}?page={page}&per_page={per_page}"
        resp = get_with_retries(u, headers, page=page)
        if resp is None or resp.status_code != 200:
            logger.error(f"Página {page}: falló permanentemente. Abortando dump completo.")
            break
        d = resp.json().get("data", [])
        logger.info(f"Página {page}: agregando {len(d)} registros")
        all_results.extend(d)

    logger.info(f"FIN de recuperación: bajadas {len(all_results)} respuestas sobre un estimado de {total} en {page} páginas.")

    # Obtener detalles del survey para mapear preguntas
    SURVEY_DETAILS_ENDPOINT = f"/v3/surveys/{survey_id}/details"
    logger.info("Recuperando detalles del survey para mapear preguntas y respuestas...")
    survey_details = requests.get(f"{HOST}{SURVEY_DETAILS_ENDPOINT}", headers=headers).json()

    choice_map = {}
    question_map = {}

    for page_data in survey_details.get("pages", []):
        for question in page_data.get("questions", []):
            question_map[question["id"]] = question["headings"][0]["heading"]
            if "answers" in question and "choices" in question["answers"]:
                for answer in question["answers"]["choices"]:
                    choice_map[answer["id"]] = answer["text"]

    # Procesar respuestas
    responses_dict = {}

    for response in all_results:
        respondent_id = response["id"]
        if respondent_id not in responses_dict:
            responses_dict[respondent_id] = {}

        responses_dict[respondent_id]['Boca'] = response.get('custom_variables', {}).get('Boca', '')
        responses_dict[respondent_id]['date_created'] = response.get('date_created', '')[:10]

        for page in response.get("pages", []):
            for question in page.get("questions", []):
                question_id = question["id"]
                for answer in question.get("answers", []):
                    if "choice_id" in answer:
                        responses_dict[respondent_id][question_id] = choice_map.get(answer["choice_id"], answer["choice_id"])
                    elif "text" in answer:
                        responses_dict[respondent_id][question_id] = answer["text"]
                    elif "row_id" in answer and "text" in answer:
                        responses_dict[respondent_id][question_id] = answer["text"]

    df_responses = pd.DataFrame.from_dict(responses_dict, orient='index')

    # Limpiar HTML (si hay columnas con texto en span, etc.)
    def extract_text_from_span(html_text):
        if not isinstance(html_text, str):
            return html_text
        return re.sub(r'<[^>]*>', '', html_text)

    if '152421787' in df_responses.columns:
        df_responses['152421787'] = df_responses['152421787'].apply(extract_text_from_span)

    # Renombrar columnas a sus títulos reales
    df_responses.rename(columns=question_map, inplace=True)
    df_responses.columns = [extract_text_from_span(col) for col in df_responses.columns]

    # luego guardado:
    logger.info("Serializando y guardando en la DB…")
    with BytesIO() as output:
        df_responses.to_pickle(output)
        binary_data = output.getvalue()
    logger.info("Limpiando tabla anterior y agregando nueva")
    db.session.query(TercerSurvey).delete()
    db.session.flush()
    db.session.add(TercerSurvey(data=binary_data))
    db.session.commit()
    elapsed = datetime.now() - hora_inicio
    logger.info(f"Survey guardado EXITOSAMENTE: {len(df_responses)} filas en {elapsed}.")
    gc.collect()