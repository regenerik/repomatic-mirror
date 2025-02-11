from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from io import BytesIO
from database import db
from models import Reporte, TodosLosReportes, Survey, AllApiesResumes, AllCommentsWithEvaluation, FilteredExperienceComments
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta
from io import BytesIO
import pytz
from dotenv import load_dotenv
load_dotenv()
import os
from logging_config import logger
import gc
# Zona horaria de São Paulo/Buenos Aires
tz = pytz.timezone('America/Sao_Paulo')

# - Creando cliente openai
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    organization="org-cSBk1UaTQMh16D7Xd9wjRUYq"
)


#-----------------------------CAPTURAR REPORTES EXISTENTES-----------------------------------
def compilar_reportes_existentes():
    # Obtener todos los reportes posibles
    todos_los_reportes = TodosLosReportes.query.all()  # Asegúrate de tener un modelo para esta tabla
    titulos_posibles = [reporte.title for reporte in todos_los_reportes]

    logger.info(f"1 - Todos los titulos de reportes posibles son: {titulos_posibles}")
    reportes_disponibles = Reporte.query.all()  # La tabla que ya tenés con reportes disponibles

    # Serializar los reportes disponibles
    reportes_disponibles_serializados = []
    for reporte in reportes_disponibles:
        created_at_utc = reporte.created_at.replace(tzinfo=pytz.utc)
        created_at_local = created_at_utc.astimezone(tz)
        reporte_dict = {
            'id': reporte.id,
            'user_id': reporte.user_id,
            'report_url': reporte.report_url,
            'title': reporte.title,
            'size_megabytes': reporte.size,
            'elapsed_time': reporte.elapsed_time,
            'created_at': created_at_local.strftime("%d/%m/%Y %H:%M:%S")
        }
        reportes_disponibles_serializados.append(reporte_dict)

    # Crear un set de URLs de reportes disponibles
    urls_disponibles = {reporte.report_url for reporte in reportes_disponibles}

    # Filtrar los reportes no disponibles
    reportes_no_disponibles_serializados = []
    for reporte in todos_los_reportes:
        if reporte.report_url not in urls_disponibles:
            reporte_dict = {
                'report_url': reporte.report_url,
                'title': reporte.title,
                'size_megabytes': None,  # Podés dejarlo en None si no tenés el tamaño para los no disponibles
                'created_at': None  # Si no hay fecha para los no disponibles, dejarlo en None
            }
            reportes_no_disponibles_serializados.append(reporte_dict)

    # Devolver ambas listas en un objeto
    return {
        'disponibles': reportes_disponibles_serializados,
        'no_disponibles': reportes_no_disponibles_serializados
    }


# ----------------------------UTILS GENERAL PARA LOGGIN SESSION Y SESSKEY--------------------

def iniciar_sesion_y_obtener_sesskey(username, password, report_url):
    session = requests.Session()
    logger.info("2 - Función Util iniciar_sesion_y_obtener_sesskey iniciando...")

    # Paso 1: Obtener el logintoken
    login_page_url = "https://www.campuscomercialypf.com/login/index.php"
    try:
        login_page_response = session.get(login_page_url, timeout=10)
        login_page_soup = BeautifulSoup(login_page_response.text, 'html.parser')
        logintoken_input = login_page_soup.find('input', {'name': 'logintoken'})
        logintoken = logintoken_input['value'] if logintoken_input else None
        logger.info("3 - Token recuperado. Iniciando log-in...")
    except requests.exceptions.RequestException as e:
        logger.info(f"Error al obtener la página de login: {e}")
        logger.info("Si llegaste a este error, puede ser que la red esté caída o la URL del campus haya cambiado.")
        return None, None

    # Paso 2: Realizar el inicio de sesión
    login_payload = {
        "username": username,
        "password": password,
        "logintoken": logintoken,
        "anchor": ""
    }
    login_headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }


    login_response = session.post(login_page_url, data=login_payload, headers=login_headers)

    if login_response.status_code == 200 and "TotaraSession" in session.cookies:
        logger.info("4 - Inicio de sesión exitoso. Comenzando a capturar el sesskey...")
    else:
        logger.info("Error en el inicio de sesión")
        return None, None

    # Paso 3: Obtener el sesskey dinámicamente desde la página
    dashboard_url = report_url
    dashboard_response = session.get(dashboard_url)
    dashboard_html = dashboard_response.text
    soup = BeautifulSoup(dashboard_html, 'html.parser')
    sesskey_link = soup.find('a', href=re.compile(r'/login/logout.php\?sesskey='))
    if sesskey_link:
        sesskey_url = sesskey_link['href']
        sesskey = re.search(r'sesskey=([a-zA-Z0-9]+)', sesskey_url)
        if sesskey:
            logger.info("5 - Sesskey recuperado.")
            return session, sesskey.group(1)
    logger.info("Error: No se pudo obtener el sesskey")
    return None, None


# -----------------------------------UTILS PARA LLAMADA SIMPLE------------------------------------

def exportar_reporte_json(username, password, report_url):
    session, sesskey = iniciar_sesion_y_obtener_sesskey(username, password, report_url)
    if not session or not sesskey:
        logger.info("Error al iniciar sesión o al obtener el sesskey.")
        return None
    
    logger.info("Recuperando reporte desde la URL...")

    # Paso 4: Traer los datos en excel
    export_payload = {
        "sesskey": sesskey,
        "_qf__report_builder_export_form": "1",
        "format": "excel",
        "export": "Exportar"
    }
    export_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": report_url
    }

    export_response = session.post(report_url, data=export_payload, headers=export_headers)
    logger.info("ESTE ES EL EXPORT RESPONSE: ", export_response)

    if export_response.status_code == 200:
        logger.info("Excel recuperado. Transformando a json...")

        # Leer el archivo Excel y convertir a JSON
        excel_data = BytesIO(export_response.content)
        df = pd.read_excel(excel_data, engine='openpyxl')
        json_data = df.to_json(orient='records')  # Convertir DataFrame a JSON
        logger.info("Enviando json de utils a la ruta...")
        return json_data

    else:
        logger.info("Error en la exportación")
        return None

# -----------------------------------UTILS PARA LLAMADA MULTIPLE------------------------------------

def exportar_y_guardar_reporte(session, sesskey, username, report_url):
    hora_inicio = datetime.now()
    logger.info(f"6 - Recuperando reporte desde la URL. Hora de inicio: {hora_inicio.strftime('%d-%m-%Y %H:%M:%S')}")

    export_payload = {
        "sesskey": sesskey,
        "_qf__report_builder_export_form": "1",
        "format": "csv",
        "export": "Exportar"
    }
    export_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": report_url
    }

    try:
        # Captura el HTML del report_url
        html_response = session.get(report_url)
        html_response.raise_for_status()
        html_content = html_response.text

        # Pre fabrica variable "titulo" por si no lo encuentra
        titulo = "reporte_solicitado"

        # Analiza el HTML con BeautifulSoup para buscar título en los <h2><span>...</span></h2>
        soup = BeautifulSoup(html_content, 'html.parser')
        h2_tags = soup.find_all('h2')
        for h2_tag in h2_tags:
            span_tags = h2_tag.find_all('span')
            for span_tag in span_tags:
                span_text = span_tag.get_text(strip=True)
                if span_text:
                    logger.info(f"7 - Texto encontrado en <span>: {span_text}")
                    # Suponiendo que los títulos válidos vienen de TodosLosReportes
                    titulos_posibles = [reporte.title for reporte in TodosLosReportes.query.all()]
                    if span_text in titulos_posibles:
                        titulo = span_text
                        break

        logger.info("8 - Comenzando la captura del archivo csv...")
        export_response = session.post(report_url, data=export_payload, headers=export_headers)
        export_response.raise_for_status()
        logger.info(f"9 - La respuesta de la captura es: {export_response}")

        # Convertimos el contenido a BytesIO
        csv_data = BytesIO(export_response.content)

        hora_descarga_finalizada = datetime.now()
        elapsed_time = hora_descarga_finalizada - hora_inicio
        elapsed_time_str = str(elapsed_time)
        logger.info(f"10 - CSV recuperado. Tiempo transcurrido de descarga: {elapsed_time}")

        # Si el reporte es 'Inscripciones Marketplace', se divide el campo APIES según la lógica
        if titulo == "Inscripciones Marketplace":
            import csv
            import re
            from io import StringIO

            logger.info("Detectado 'Inscripciones Marketplace'; se procederá a dividir registros con múltiples APIES.")
            csv_data.seek(0)
            decoded_csv = csv_data.read().decode('utf-8', errors='replace')
            lines = decoded_csv.splitlines()

            reader = csv.DictReader(lines)
            fieldnames = reader.fieldnames
            filas_procesadas = []

            for row in reader:
                apies_str = row.get('APIES', '')
                apies_str = re.sub(r'[–—−]', '-', apies_str)
                apies_str = re.sub(r'[\u200B\u200C\u200D\uFEFF]', '', apies_str)
                apies_list = [apie.strip() for apie in apies_str.split('-')]
                apies_unicos = list(dict.fromkeys(apies_list))

                if len(apies_unicos) > 1:
                    for api_value in apies_unicos:
                        nueva_fila = dict(row)
                        nueva_fila['APIES'] = api_value
                        filas_procesadas.append(nueva_fila)
                else:
                    if len(apies_unicos) == 1:
                        row['APIES'] = apies_unicos[0]
                    else:
                        row['APIES'] = ''
                    filas_procesadas.append(row)

            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(filas_procesadas)
            csv_data = BytesIO(output.getvalue().encode('utf-8'))
            logger.info("Operación de división de APIES completada para 'Inscripciones Marketplace'.")

        size_megabytes = len(csv_data.getvalue()) / 1_048_576
        logger.info("11 - Controlando cantidad de reportes previos en la DB para mantener sólo los últimos 7...")

        if report_url in [
            "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=133",
            "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=306"
        ]:
            max_reports = 30
        else:
            max_reports = 7

        # Se consulta la cantidad de reportes existentes para esa URL, ordenados por fecha de creación ascendente (el más viejo primero)
        existing_reports = Reporte.query.filter_by(report_url=report_url).order_by(Reporte.created_at.asc()).all()
        # Si hay 7 o más, se elimina el/los más viejo(s) hasta dejar espacio para el nuevo
        while len(existing_reports) >= max_reports:
            oldest_report = existing_reports[0]
            db.session.delete(oldest_report)
            db.session.commit()  # Commit inmediato para que la lista se actualice
            logger.info("Reporte más antiguo eliminado para mantener solo los últimos 7 registros.")
            existing_reports = Reporte.query.filter_by(report_url=report_url).order_by(Reporte.created_at.asc()).all()

        # Guardamos el nuevo reporte
        report = Reporte(
            user_id=username,
            report_url=report_url,
            data=csv_data.read(),
            size=size_megabytes,
            elapsed_time=elapsed_time_str,
            title=titulo
        )
        db.session.add(report)
        db.session.commit()
        logger.info("13 - Reporte nuevo guardado en la base de datos. Fin de la ejecución.")
        return

    except requests.RequestException as e:
        logger.info(f"Error en la recuperación del reporte desde el campus. El siguiente error se recuperó: {e}")
    except SQLAlchemyError as e:
        logger.info(f"Error en la base de datos: {e}")
    except Exception as e:
        logger.info(f"Error inesperado: {e}")


def obtener_reporte(reporte_url):
    report = Reporte.query.filter_by(report_url=reporte_url).order_by(Reporte.created_at.desc()).first()
    if report:
        logger.info("3 - Reporte encontrado en db")
        return report.data, report.created_at, report.title
    else:
        return None, None, None

