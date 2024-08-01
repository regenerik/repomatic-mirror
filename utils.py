import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from io import BytesIO
from database import db
from models import Reporte
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import pytz
from logging_config import logger
# Zona horaria de São Paulo/Buenos Aires
tz = pytz.timezone('America/Sao_Paulo')

#-----------------------------CAPTURAR REPORTES EXISTENTES-----------------------------------
def compilar_reportes_existentes():
    reportes = Reporte.query.all()
    reportes_serializados = []

    for reporte in reportes:
        # Convertir la fecha de UTC a la zona horaria local
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
        reportes_serializados.append(reporte_dict)

    return reportes_serializados

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

    # Paso 4: Traer los datos en excel
    # export_payload = {
    #     "sesskey": sesskey,
    #     "_qf__report_builder_export_form": "1",
    #     "format": "excel",
    #     "export": "Exportar"
    # }

        # Paso 4: Traer los datos en csv
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
        html_response.raise_for_status()  # Lanza una excepción para respuestas de error HTTP

        # # Imprime una parte del HTML para depuración
        html_content = html_response.text


        # Pre fabrica variable "titulo" por si no lo encuentra
        titulo = "reporte_solicitado"

        # Analiza el HTML con BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Busca todos los <h2> en el HTML
        h2_tags = soup.find_all('h2')
        for h2_tag in h2_tags:
            # Busca todos los <span> dentro del <h2>
            span_tags = h2_tag.find_all('span')
            for span_tag in span_tags:
                # Captura el texto del <span>
                span_text = span_tag.get_text(strip=True)
                if span_text:
                    # Aquí puedes implementar lógica adicional para verificar el texto
                    # Por ejemplo, podrías verificar si contiene ciertas palabras clave
                    logger.info(f"7 - Texto encontrado en <span>: {span_text}")
                    # Lista con los títulos posibles
                    titulos_posibles = [
                        "USUARIOS POR ASIGNACION PARA GESTORES",
                        "CURSADA+YPFRESPALDO",
                        "Cursos con detalle",
                        "VERIFICA USUARIOS PARA GESTORES",
                        "AVANCE DE PROGRAMAS"
                    ]

                    # Verificamos si span_text está en la lista de títulos posibles
                    if span_text in titulos_posibles:
                        titulo = span_text
                        break

        logger.info(f"8 - Comenzando la captura del archivo csv...")

        # AHORA LA CAPTURA DEL MISMÍSIMO ARCHIVO CSV
        export_response = session.post(report_url, data=export_payload, headers=export_headers)
        export_response.raise_for_status()  # Lanza una excepción para respuestas de error HTTP

        logger.info(f"9 - La respuesta de la captura es: {export_response}")
        

        # Captura la hora de finalización
        hora_descarga_finalizada = datetime.now()

        # Calcula el intervalo de tiempo
        elapsed_time = hora_descarga_finalizada - hora_inicio
        elapsed_time_str = str(elapsed_time)
        logger.info(f"10 - CSV recuperado. Tiempo transcurrido de descarga: {elapsed_time}")

        

        # Si es tabla "usuario por asignacion para gestores", toquetear:

        if "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=133" in report_url:
            csv_data_raw = pd.read_csv(BytesIO(export_response.content))
            csv_data_raw = csv_data_raw.loc[csv_data_raw['DNI'].str.isnumeric()]
            csv_buffer = BytesIO()
            csv_data_raw.to_csv(csv_buffer, index=False)
            csv_data_raw_bytes = csv_buffer.getvalue()
            csv_data = BytesIO(csv_data_raw_bytes)
        else:
            csv_data = BytesIO(export_response.content)
        # Pasamos el csv a binario y rescatamos el peso
        # csv_data = BytesIO(export_response.content)

        size_megabytes = (len(csv_data.getvalue())) / 1_048_576
        logger.info("11 - Eliminando reporte anterior de DB...")
        # Elimina registros previos en la tabla que corresponde
        report_to_delete = Reporte.query.filter_by(report_url=report_url).order_by(Reporte.created_at.desc()).first()
        if report_to_delete:
            db.session.delete(report_to_delete)
            db.session.commit()
            logger.info("12 - Reporte previo eliminado >>> guardando el nuevo...")

        # Instancia el nuevo registro a la tabla que corresponde y guarda en db
        report = Reporte(user_id=username, report_url=report_url, data=csv_data.read(),size= size_megabytes, elapsed_time= elapsed_time_str, title=titulo)
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
        created_at_utc = report.created_at.replace(tzinfo=pytz.utc)
        created_at_local = created_at_utc.astimezone(tz)
        logger.info("3 - Reporte encontrado en db")
        created_at_bsas = created_at_local.strftime("%d/%m/%Y %H:%M:%S")
        return report.data, created_at_bsas, report.title
    else:
        return None, None, None

