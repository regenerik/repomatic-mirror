import requests
from bs4 import BeautifulSoup
import re
import tempfile
import time

# Variable para almacenar el progreso
progress = {"status": "iniciado", "percent": 0, "error": None, "result": None}

def obtener_sesskey(html):
    soup = BeautifulSoup(html, 'html.parser')
    sesskey_link = soup.find('a', href=re.compile(r'/login/logout.php\?sesskey='))
    if sesskey_link:
        sesskey_url = sesskey_link['href']
        sesskey = re.search(r'sesskey=([a-zA-Z0-9]+)', sesskey_url)
        if sesskey:
            return sesskey.group(1)
    return None

def exportar_reporte_excel(username, password):
    global progress
    progress = {"status": "iniciado", "percent": 0, "error": None, "result": None}

    try:
        session = requests.Session()

        # Paso 1: Obtener el logintoken
        login_page_url = "https://www.campuscomercialypf.com/login/index.php"
        login_page_response = session.get(login_page_url)
        progress["percent"] = 10

        login_page_soup = BeautifulSoup(login_page_response.text, 'html.parser')
        logintoken_input = login_page_soup.find('input', {'name': 'logintoken'})
        logintoken = logintoken_input['value'] if logintoken_input else None

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
        progress["percent"] = 30

        # Verificar si se ha iniciado sesión correctamente
        if login_response.status_code == 200 and "TotaraSession" in session.cookies:
            print("Inicio de sesión exitoso")
        else:
            raise Exception("Error en el inicio de sesión")

        # Paso 3: Obtener el sesskey dinámicamente desde la página
        dashboard_url = "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=133"
        dashboard_response = session.get(dashboard_url)
        dashboard_html = dashboard_response.text
        sesskey = obtener_sesskey(dashboard_html)

        # Verificar si se pudo obtener el sesskey
        if not sesskey:
            raise Exception("Error: No se pudo obtener el sesskey")
        
        progress["percent"] = 50

        # Paso 4: Seleccionar "Excel" como formato de exportación y exportar el archivo
        export_payload = {
            "sesskey": sesskey,
            "_qf__report_builder_export_form": "1",
            "format": "excel",
            "export": "Exportar"
        }
        export_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": dashboard_url
        }

        export_response = session.post(dashboard_url, data=export_payload, headers=export_headers)

        # Verificar la respuesta de la exportación
        if export_response.status_code == 200:
            print("Exportación exitosa")
            progress["percent"] = 90

            # Crear un archivo temporal y escribir el contenido de export_response en él
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(export_response.content)

            progress["percent"] = 100
            progress["status"] = "completo"
            progress["result"] = temp_file.name  # Guardar el nombre del archivo temporal en el progreso

            return temp_file.name  # Devolver el nombre del archivo temporal
        else:
            raise Exception("Error en la exportación")

    except Exception as e:
        progress["status"] = "error"
        progress["error"] = str(e)
        return None

def get_progress():
    global progress
    return progress
