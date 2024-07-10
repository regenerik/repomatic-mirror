import requests
from bs4 import BeautifulSoup

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
    # print(login_response.status_code, login_response.text)
    exit()
