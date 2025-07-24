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

# 👉 Función que maneja retries automáticos con backoff exponencial para errores 429
def get_with_retries(url, headers, max_retries=5, backoff_base=1.5):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                wait_time = backoff_base * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Rate limited (429). Reintentando en {wait_time:.2f}s (intento {attempt+1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                logger.error(f"Error inesperado al obtener respuestas: {response.status_code}")
                break
        except Exception as e:
            logger.error(f"Excepción durante el request: {e}")
            time.sleep(2)
    return None

# 👉 Función principal que recupera y guarda el survey
def obtener_y_guardar_survey():
    api_key = os.getenv('SURVEYMONKEY_API_KEY')
    access_token = os.getenv('SURVEYMONKEY_ACCESS_TOKEN')
    survey_id = '416779463'
    
    logger.info("Arrancando con el tercer survey ... vamos que esta sale a la primera..")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    HOST = "https://api.surveymonkey.com"
    SURVEY_RESPONSES_ENDPOINT = f"/v3/surveys/{survey_id}/responses/bulk"
    SURVEY_DETAILS_ENDPOINT = f"/v3/surveys/{survey_id}/details"

    hora_inicio = datetime.now()
    logger.info("Recuperando detalles del survey nuevo...")

    survey_details = requests.get(f"{HOST}{SURVEY_DETAILS_ENDPOINT}", headers=headers).json()

    # Mapeo de preguntas y opciones
    choice_map = {}
    question_map = {}
    for page in survey_details.get("pages", []):
        for question in page.get("questions", []):
            question_map[question["id"]] = question["headings"][0]["heading"]
            if "answers" in question and "choices" in question["answers"]:
                for answer in question["answers"]["choices"]:
                    choice_map[answer["id"]] = answer["text"]

    logger.info("Bajando respuestas... ¡aguantá que esto se pone copado!")
    page = 1
    per_page = 10000
    all_responses = []

    while True:
        url = f"{HOST}{SURVEY_RESPONSES_ENDPOINT}?page={page}&per_page={per_page}"
        response_data = get_with_retries(url, headers)

        if response_data is None:
            logger.error("No se pudo recuperar respuestas luego de varios intentos.")
            break

        responses_json = response_data.json().get("data", [])
        if not responses_json:
            break

        all_responses.extend(responses_json)
        page += 1

    logger.info("Procesando respuestas... que no se nos escape nada")
    responses_dict = {}

    for response in all_responses:
        respondent_id = response["id"]
        if respondent_id not in responses_dict:
            responses_dict[respondent_id] = {}

        responses_dict[respondent_id]['Boca'] = response.get('custom_variables', {}).get('Boca', '')
        responses_dict[respondent_id]['date_created'] = response.get('date_created', '')[:10]

        for page_data in response.get("pages", []):
            for question in page_data.get("questions", []):
                question_id = question["id"]
                for answer in question.get("answers", []):
                    if "choice_id" in answer:
                        responses_dict[respondent_id][question_id] = choice_map.get(answer["choice_id"], answer["choice_id"])
                    elif "text" in answer:
                        responses_dict[respondent_id][question_id] = answer["text"]
                    elif "row_id" in answer and "text" in answer:
                        responses_dict[respondent_id][question_id] = answer["text"]

    df_responses = pd.DataFrame.from_dict(responses_dict, orient='index')
    all_responses = []  # Limpiamos memoria

    # Limpiar HTML
    def extract_text_from_span(html_text):
        if not isinstance(html_text, str):
            return html_text
        return re.sub(r'<[^>]*>', '', html_text)

    if '152421787' in df_responses.columns:
        df_responses['152421787'] = df_responses['152421787'].apply(extract_text_from_span)

    df_responses.rename(columns=question_map, inplace=True)
    df_responses.columns = [extract_text_from_span(col) for col in df_responses.columns]

    logger.info(f"DataFrame armado: {df_responses.shape[0]} filas y {df_responses.shape[1]} columnas.")

    # Serializar
    logger.info("Serializando DataFrame para guardarlo en la DB...")
    with BytesIO() as output:
        df_responses.to_pickle(output)
        binary_data = output.getvalue()

    logger.info("Guardando el survey nuevo en la DB... a meterle garra")
    db.session.query(TercerSurvey).delete()
    db.session.flush()

    new_survey = TercerSurvey(data=binary_data)
    db.session.add(new_survey)
    db.session.commit()

    elapsed_time = datetime.now() - hora_inicio
    logger.info(f"Survey nuevo guardado. Tiempo transcurrido: {elapsed_time}")

    gc.collect()
    return