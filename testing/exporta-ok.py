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

# Paso 4: Seleccionar "Excel" como formato de exportación y exportar el archivo
export_url = "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=133"
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

export_response = session.post(export_url, data=export_payload, headers=export_headers)

# Verificar la respuesta de la exportación
if export_response.status_code == 200:
    print("Exportación exitosa")
    # Guardar el archivo de Excel
    with open('reporte_excel.xlsx', 'wb') as f:
        f.write(export_response.content)
    print("Archivo de Excel guardado correctamente")
else:
    print("Error en la exportación")
    # print(export_response.status_code, export_response.text)
