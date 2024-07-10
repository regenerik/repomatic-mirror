import requests
from bs4 import BeautifulSoup
import re

# Función para obtener el sesskey desde el HTML de la página
def obtener_sesskey(html):
    soup = BeautifulSoup(html, 'html.parser')
    sesskey_link = soup.find('a', href=re.compile(r'/login/logout.php\?sesskey='))
    if sesskey_link:
        sesskey_url = sesskey_link['href']
        # Extraer el sesskey del URL
        sesskey = re.search(r'sesskey=([a-zA-Z0-9]+)', sesskey_url)
        if sesskey:
            return sesskey.group(1)
    return None

# Crear una sesión
session = requests.Session()

# Paso 1: Obtener el logintoken
login_page_url = "https://www.campuscomercialypf.com/login/index.php"
login_page_response = session.get(login_page_url)
login_page_soup = BeautifulSoup(login_page_response.text, 'html.parser')
logintoken_input = login_page_soup.find('input', {'name': 'logintoken'})
logintoken = logintoken_input['value'] if logintoken_input else None

# Paso 2: Realizar el inicio de sesión
login_url = "https://www.campuscomercialypf.com/login/index.php"
login_payload = {
    "username": "34490395",
    "password": "mentira1",
    "logintoken": logintoken,
    "anchor": ""
}
login_headers = {
    "Content-Type": "application/x-www-form-urlencoded"
}

login_response = session.post(login_url, data=login_payload, headers=login_headers)

# Verificar si se ha iniciado sesión correctamente
if login_response.status_code == 200 and "TotaraSession" in session.cookies:
    print("Inicio de sesión exitoso")
else:
    print("Error en el inicio de sesión")
    print(login_response.status_code, login_response.text)
    exit()

# Paso 3: Obtener el sesskey dinámicamente desde la página donde se encuentra
dashboard_url = "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=133"
dashboard_response = session.get(dashboard_url)
dashboard_html = dashboard_response.text
sesskey = obtener_sesskey(dashboard_html)

# Verificar si se pudo obtener el sesskey
if sesskey:
    print(f"Sesskey obtenido correctamente: {sesskey}")
else:
    print("Error: No se pudo obtener el sesskey")
    exit()

# Paso 4: Realizar la solicitud del reporte específico (Usuarios por asignación para gestores)
report_url = "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=133"
report_payload = {
    "sesskey": sesskey,
    "_qf__report_builder_standard_search_form": "1",
    "mform_showmore_id_newfilterstandard": "0",
    "mform_isexpanded_id_newfilterstandard": "1",
    "user-username_op": "0",
    "user-username": "",
    "user-fullname_op": "0",
    "user-fullname": "",
    "pos-fullname_op": "0",
    "pos-fullname": "",
    "org-fullname_op": "0",
    "org-fullname": "",
    "user-deleted": "",
    "submitgroupstandard[addfilter]": "Búsqueda"
}
report_headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": dashboard_url
}

report_response = session.post(report_url, data=report_payload, headers=report_headers)

# Verificar la respuesta del reporte
if report_response.status_code == 200:
    print("Solicitud del reporte exitosa")
    # Aquí puedes procesar el reporte, por ejemplo:
    # print(report_response.text)
else:
    print("Error en la solicitud del reporte")
    # print(report_response.status_code, report_response.text)
