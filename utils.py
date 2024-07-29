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
            'size_megabytes': reporte.size,
            'elapsed_time': reporte.elapsed_time,
            'created_at': created_at_local.strftime("%d/%m/%Y %H:%M:%S")

        }
        reportes_serializados.append(reporte_dict)

    return reportes_serializados

# ----------------------------UTILS GENERAL PARA LOGGIN SESSION Y SESSKEY--------------------

def iniciar_sesion_y_obtener_sesskey(username, password, report_url):
    session = requests.Session()
    print("Utils iniciando. Entrando y recuperando token inicial...")

    # Paso 1: Obtener el logintoken
    login_page_url = "https://www.campuscomercialypf.com/login/index.php"
    login_page_response = session.get(login_page_url)
    login_page_soup = BeautifulSoup(login_page_response.text, 'html.parser')
    logintoken_input = login_page_soup.find('input', {'name': 'logintoken'})
    logintoken = logintoken_input['value'] if logintoken_input else None
    print("Token recuperado. Iniciando login")

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
        print("Inicio de sesión exitoso")
    else:
        print("Error en el inicio de sesión")
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
            print("Sesskey recuperado.")
            return session, sesskey.group(1)
    print("Error: No se pudo obtener el sesskey")
    return None, None


# -----------------------------------UTILS PARA LLAMADA SIMPLE------------------------------------

def exportar_reporte_json(username, password, report_url):
    session, sesskey = iniciar_sesion_y_obtener_sesskey(username, password, report_url)
    if not session or not sesskey:
        print("Error al iniciar sesión o al obtener el sesskey.")
        return None
    
    print("Recuperando reporte desde la URL...")

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
    print("ESTE ES EL EXPORT RESPONSE: ", export_response)

    if export_response.status_code == 200:
        print("Excel recuperado. Transformando a json...")

        # Leer el archivo Excel y convertir a JSON
        excel_data = BytesIO(export_response.content)
        df = pd.read_excel(excel_data, engine='openpyxl')
        json_data = df.to_json(orient='records')  # Convertir DataFrame a JSON
        print("Enviando json de utils a la ruta...")
        return json_data

    else:
        print("Error en la exportación")
        return None

# -----------------------------------UTILS PARA LLAMADA MULTIPLE------------------------------------

def exportar_y_guardar_reporte(session, sesskey, username, report_url):

    hora_inicio = datetime.now()
    print(f"Recuperando reporte desde la URL... Hora de inicio: {hora_inicio.strftime('%d-%m-%Y %H:%M:%S')}")

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
            export_response = session.post(report_url, data=export_payload, headers=export_headers)
            export_response.raise_for_status()  # Lanza una excepción para respuestas de error HTTP

            print("ESTE ES EL EXPORT RESPONSE: ", export_response)
            

            # Captura la hora de finalización
            hora_descarga_finalizada = datetime.now()

            # Calcula el intervalo de tiempo
            elapsed_time = hora_descarga_finalizada - hora_inicio
            elapsed_time_str = str(elapsed_time)
            print(f"CSV recuperado. Tiempo transcurrido de descarga: {elapsed_time}")

            print("Ahora guardando en la base de datos...")

            # Pasamos el excel a binario y rescatamos el peso
            csv_data = BytesIO(export_response.content)

            size_megabytes = (len(csv_data.getvalue())) / 1_048_576

            # Elimina registros previos en la tabla que corresponde
            report_to_delete = Reporte.query.filter_by(report_url=report_url).order_by(Reporte.created_at.desc()).first()
            if report_to_delete:
                db.session.delete(report_to_delete)
                db.session.commit()
                print("Reporte previo eliminado >>> guardando el nuevo...")

            # Instancia el nuevo registro a la tabla que corresponde y guarda en db
            report = Reporte(user_id=username, report_url=report_url, data=csv_data.read(),size= size_megabytes, elapsed_time= elapsed_time_str)
            db.session.add(report)
            db.session.commit()
            print("Reporte nuevo guardado en la base de datos.")
            return

    except requests.RequestException as e:
        print(f"Error en la recuperación del reporte desde el campus. El siguiente error se recuperó: {e}")

    except SQLAlchemyError as e:
        print(f"Error en la base de datos: {e}")

    except Exception as e:
        print(f"Error inesperado: {e}")



def obtener_reporte(reporte_url, username):


    report = Reporte.query.filter_by(report_url=reporte_url).order_by(Reporte.created_at.desc()).first()
    if report:
        return report.data
    else:
        return None
