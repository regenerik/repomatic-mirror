import openai
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from io import BytesIO
from database import db
from models import Reporte, TodosLosReportes, Survey, AllApiesResumes, AllCommentsWithEvaluation
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
client = openai.OpenAI(
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

        # # Captura HTML para depuración
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

                    # Lista con los títulos posibles / deprecado , ahora capturo los titulos posibles de la precarga de reportes de app.py
                    # titulos_posibles = [
                    #     "USUARIOS POR ASIGNACION PARA GESTORES",
                    #     "CURSADA+YPFRESPALDO",
                    #     "Cursos con detalle",
                    #     "VERIFICA USUARIOS PARA GESTORES",
                    #     "AVANCE DE PROGRAMAS PBI",
                    # ]

                    # Obtener todos los títulos de la base de datos
                    titulos_posibles = [reporte.title for reporte in TodosLosReportes.query.all()]

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

        

        # Si es tabla "usuario por asignacion para gestores", toquetear ( en test de falla ):

        # if "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=133" in report_url:
        #     csv_data_raw = pd.read_csv(BytesIO(export_response.content))
        #     csv_data_raw = csv_data_raw.loc[csv_data_raw['DNI'].str.isnumeric()]
        #     csv_buffer = BytesIO()
        #     csv_data_raw.to_csv(csv_buffer, index=False)
        #     csv_data_raw_bytes = csv_buffer.getvalue()
        #     csv_data = BytesIO(csv_data_raw_bytes)
        # else:
        #     csv_data = BytesIO(export_response.content)
        # Pasamos el csv a binario y rescatamos el peso
        csv_data = BytesIO(export_response.content)

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
        logger.info("3 - Reporte encontrado en db")
        return report.data, report.created_at, report.title
    else:
        return None, None, None



#-------------------------------------------------------UTILS PARA EXPERIENCIA DE USUARIO--------------------

def get_resumes(file_content):
    # Leer el archivo Excel desde el contenido en memoria (file_content)
    df = pd.read_excel(file_content)

    # Crear un diccionario para agrupar los comentarios por APIES
    comentarios_por_apies = {}
    for apies, comentario in zip(df['APIES'], df['COMENTARIO']):
        if apies not in comentarios_por_apies:
            comentarios_por_apies[apies] = []
        comentarios_por_apies[apies].append(comentario)

    # Recorrer cada APIES y crear el prompt para OpenAI
    resultados = []
    pedido = 0
    for apies, comentarios in comentarios_por_apies.items():
        prompt = f"""
        A continuación, tienes una lista de comentarios de clientes sobre la estación de servicio {apies}. Necesito que realices un resumen **sin sesgos** de los comentarios y respondas las siguientes indicaciones:

        1. **Resumen de comentarios sin sesgos**: Proporciona un análisis claro de los comentarios de los clientes. Si se mencionan nombres, citarlos en la respuesta con el motivo.
        
        2. **Temáticas más comentadas**:  Mostrar porcentaje de cada temática mencionada sobre la totalidad. Ordena las temáticas desde la más comentada hasta la menos comentada, identificando las quejas o comentarios más recurrentes. Si se mencionan nombres, citarlos en la respuesta con el motivo.

        3. **Motivos del malestar o quejas**:  Enfócate en el **motivo** que genera el malestar o la queja, no en la queja en sí. Mostrar porcentaje de comentarios de cada motivo de queja sobre la totalidad de los comentarios.  Si se mencionan nombres, citarlos en la respuesta con el motivo.

        4. **Puntaje de tópicos mencionados**: Si se mencionan algunos de los siguientes tópicos, proporciona un puntaje del 1 al 10 basado en el porcentaje de comentarios positivos sobre la totalidad de comentarios en cada uno. Si no hay comentarios sobre un tópico, simplemente coloca "-".
        
        - **A** (Atención al cliente)
        - **T** (Tiempo de espera)
        - **S** (Sanitarios)

        El puntaje se determina de la siguiente forma:
        - Si entre 90% y 99% de los comentarios totales de uno de los 3 tópicos son positivos, el puntaje es 9, en el tópico correspondiente.
        - Si el 100% de los comentarios totales  de uno de los 3 tópicos son positivos, el puntaje es 10, en el tópico correspondiente.
        - Si entre 80% y el 89% de los comentarios totales de uno de los 3 tópicos son positivos, el puntaje es 8, en el tópico correspondiente. y así sucesivamente.

        **Esta es la lista de comentarios para el análisis:**
        {comentarios}

        **Proporción y puntaje para cada tópico mencionado:**
        1. Atención al cliente (A): \[Porcentaje de comentarios positivos\] — Puntaje del 1 al 10.
        2. Tiempo de espera (T): \[Porcentaje de comentarios positivos\] — Puntaje del 1 al 10.
        3. Sanitarios (S): \[Porcentaje de comentarios positivos\] — Puntaje del 1 al 10.

        **Código Resumen**:

        ##APIES {apies}-A:5,T:Y,S:8## ( los puntajes son meramente demostrativos para entender el formato que espero de la respuesta )
        """

        try:
            pedido = pedido + 1
            print(f"El promp numero: {pedido}, está en proceso...")
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un analista que clasifica comentarios sobre eficiencia."},
                    {"role": "user", "content": prompt}
                ]
            )

            # Acceder directamente al mensaje completo como en el código funcional
            resumen = completion.choices[0].message.content
            resultados.append(f"APIES {apies}:\n{resumen}\n")

        except Exception as e:
            resultados.append(f"Ocurrió un error al procesar el APIES {apies}: {e}\n")

    # # Retornar el resultado en lugar de guardar un archivo
    # return "\n".join(resultados)

        # Ahora procesamos los resultados para extraer los puntajes y construir el archivo Excel
    data = []

    for resultado in resultados:
        apies_match = re.search(r"APIES (\d+)", resultado)
        if apies_match:
            apies = apies_match.group(1)

        # Usamos expresiones regulares para extraer los puntajes A, T, S
        a_match = re.search(r"A:(\d+)", resultado)
        t_match = re.search(r"T:(\d+)", resultado)
        s_match = re.search(r"S:(\d+)", resultado)

        a_score = int(a_match.group(1)) if a_match else "-"
        t_score = int(t_match.group(1)) if t_match else "-"
        s_score = int(s_match.group(1)) if s_match else "-"

        # Agregamos una fila a nuestra lista de datos, incluyendo el resumen completo
        data.append({
            "APIES": apies,
            "ATENCION AL CLIENTE": a_score,
            "TIEMPO DE ESPERA": t_score,
            "SANITARIOS": s_score,
            "RESUMEN": resultado
        })

    # Crear un DataFrame con los resultados
    df_resultados = pd.DataFrame(data)

    # Crear un archivo Excel en memoria
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_resultados.to_excel(writer, index=False, sheet_name='Resúmenes')

    # Volver al inicio del archivo para que Flask pueda leerlo
    output.seek(0)

    # Retornar el archivo Excel en memoria
    return output

#----------------UTILS PARA OBTENER TODOS LOS RESUMENES>>>>>>>>>>>>>>>>>>>>>>>>>>

def get_resumes_of_all(file_content):
    logger.info("4 - Util get_resumes_of_all inicializado")
    # Leer el archivo Excel desde el contenido en memoria (file_content)

    logger.info("5 - Leyendo excel y transformando fechas...")
    df = pd.read_excel(BytesIO(file_content))

    # Convertir la columna de fechas a tipo datetime
    df['FECHA'] = pd.to_datetime(df['FECHA'], format='%d/%m/%Y')

    # Obtener la fecha sin hora
    df['FECHA'] = df['FECHA'].dt.date

    # tests
    # logger.info(f"Fechas convertidas: {df['FECHA'].head()}")
    # df_septiembre = df[df['FECHA'] == '2024-09-01']
    # logger.info(f"Registros del 1 de septiembre: {len(df_septiembre)}")


    logger.info("6 - Filtrando comentarios por fecha ( solo aparecen las del ultimo mes cerrado )...")
    # Obtener el primer día del mes actual y restar un mes para el primer día del mes pasado
    hoy = datetime.today()
    primer_dia_mes_actual = hoy.replace(day=1)
    primer_dia_mes_pasado = primer_dia_mes_actual - pd.DateOffset(months=1)

    # Obtener el último día del mes pasado
    ultimo_dia_mes_pasado = primer_dia_mes_actual - timedelta(days=1)

    # Verificar fechas
    logger.info(f"Primer día del mes pasado: {primer_dia_mes_pasado}")
    logger.info(f"Último día del mes pasado: {ultimo_dia_mes_pasado}")
    logger.info(f"Fechas únicas en el archivo: {df['FECHA'].unique()}")

    # Filtrar los comentarios entre el primer y el último día del mes pasado
    df_filtrado = df[(df['FECHA'] >= primer_dia_mes_pasado.date()) & (df['FECHA'] <= ultimo_dia_mes_pasado.date())]

    logger.info(f"Comentarios filtrados: {len(df_filtrado)}")

    logger.info("7 - Agrupando comentarios según APIES...")
    # Crear un diccionario para agrupar los comentarios por APIES
    comentarios_por_apies = {}
    for apies, comentario in zip(df_filtrado['APIES'], df_filtrado['COMENTARIO']):
        if apies not in comentarios_por_apies:
            comentarios_por_apies[apies] = []
        comentarios_por_apies[apies].append(comentario)

    cantidad_apies = len(comentarios_por_apies)
    logger.info(f"8 - La cantidad de Apies a ser procesadas por OPENAI es de : {cantidad_apies}, esto puede tomar un tiempo...")

    # Recorrer cada APIES y crear el prompt para OpenAI
    resultados = []
    pedido = 0
    for apies, comentarios in comentarios_por_apies.items():
        prompt = f"""
        A continuación, tienes una lista de comentarios de clientes sobre la estación de servicio {apies}. Necesito que realices un resumen **sin sesgos** de los comentarios y respondas las siguientes indicaciones:
        (En tu respuesta, respeta los títulos como se encuentran escritos)
        1. **Resumen de comentarios sin sesgos**: Proporciona un análisis claro de los comentarios de los clientes. Si se mencionan nombres, citarlos en la respuesta con el motivo.
        
        2. **Temáticas más comentadas**:  Mostrar porcentaje de cada temática mencionada sobre la totalidad. Ordena las temáticas desde la más comentada hasta la menos comentada, identificando las quejas o comentarios más recurrentes. Si se mencionan nombres, citarlos en la respuesta con el motivo.

        3. **Motivos del malestar o quejas**:  Enfócate en el **motivo** que genera el malestar o la queja, no en la queja en sí. Mostrar porcentaje de comentarios de cada motivo de queja sobre la totalidad de los comentarios.  Si se mencionan nombres, citarlos en la respuesta con el motivo.

        4. **Puntaje de tópicos mencionados**: Si se mencionan algunos de los siguientes tópicos, proporciona un puntaje del 1 al 10 basado en el porcentaje de comentarios positivos sobre la totalidad de comentarios en cada uno. Si no hay comentarios sobre un tópico, coloca exactamente el guion `-`, sin ceros o cualquier otro valor.
        
        - **A** (Atención al cliente)
        - **T** (Tiempo de espera)
        - **S** (Sanitarios)

        El puntaje se determina de la siguiente forma:
        - Si entre 90% y 99% de los comentarios totales de uno de los 3 tópicos son positivos, el puntaje es 9, en el tópico correspondiente.
        - Si el 100% de los comentarios totales  de uno de los 3 tópicos son positivos, el puntaje es 10, en el tópico correspondiente.
        - Si entre 80% y el 89% de los comentarios totales de uno de los 3 tópicos son positivos, el puntaje es 8, en el tópico correspondiente. y así sucesivamente.
        - Si hay un 0% de comentarios de un tópico, coloca exactamente el guion `-`.

        **Esta es la lista de comentarios para el análisis:**
        {comentarios}

        **Proporción y puntaje para cada tópico mencionado:**
        1. Atención al cliente (A): \[Porcentaje de comentarios positivos\] — Puntaje del 1 al 10.
        2. Tiempo de espera (T): \[Porcentaje de comentarios positivos\] — Puntaje del 1 al 10.
        3. Sanitarios (S): \[Porcentaje de comentarios positivos\] — Puntaje del 1 al 10.

        **Código Resumen**:

        ## APIES {apies}-A:5,T:Y,S:8 ## ( los puntajes son meramente demostrativos para entender el formato que espero de la respuesta )
        Este es un ejemplo de formato de respuesta de **Código Resumen** que tiene que ser respetado:  **Código Resumen**:    ## APIES 4-A:10,T:10,S:10 ##

        **Porcentajes totales**:
        Proporciona los porcentajes totales de comentarios positivos, negativos y neutros en el siguiente formato:
        POS:xx%,NEG:xx%,NEU:xx%

        """

        try:
            pedido = pedido + 1
            # print(f"El promp numero: {pedido}, está en proceso...")
            logger.info(f"El promp numero: {pedido}, está en proceso...")
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un analista que clasifica comentarios sobre eficiencia."},
                    {"role": "user", "content": prompt}
                ]
            )

            # Acceder directamente al mensaje completo como en el código funcional
            resumen = completion.choices[0].message.content
            resultados.append(f"APIES {apies}:\n{resumen}\n")

        except Exception as e:
            logger.info(f"Error en el promp numero: {pedido}, {str(e)}")
            resultados.append(f"Ocurrió un error al procesar el APIES {apies}: {e}\n")

    # # Retornar el resultado en lugar de guardar un archivo
    # return "\n".join(resultados)
    logger.info("9 - Proceso de OPENAI finalizado.")
    logger.info("10 - Procesando resultados...")
        # Ahora procesamos los resultados para extraer los puntajes y construir el archivo Excel
    data = []

    for resultado in resultados:
        apies_match = re.search(r"APIES (\d+)", resultado)
        if apies_match:
            apies = apies_match.group(1)
        else:
            apies = "-"
            logger.info(f"No se encontró el puntaje para A en APIES {apies}")

        # Usamos expresiones regulares para extraer los puntajes A, T, S
        a_match = re.search(r"A:(\d+|-)", resultado)
        t_match = re.search(r"T:(\d+|-)", resultado)
        s_match = re.search(r"S:(\d+|-)", resultado)

        # Asegurarse de que los puntajes se busquen después de "APIES"
        regex_puntajes = re.search(r"APIES.*?A:(\d+|[-]),T:(\d+|[-]|0),S:(\d+|[-]|0)", resultado)

        a_score = int(regex_puntajes.group(1)) if regex_puntajes and regex_puntajes.group(1).isdigit() else "-"
        t_score = int(regex_puntajes.group(2)) if regex_puntajes and regex_puntajes.group(2).isdigit() else "-"
        s_score = int(regex_puntajes.group(3)) if regex_puntajes and regex_puntajes.group(3).isdigit() else "-"

        # Expresión regular ajustada para capturar los porcentajes con o sin espacios
        porcentajes_match = re.search(r"POS:\s*(\d+\.?\d*)%.*?NEG:\s*(\d+\.?\d*)%.*?NEU:\s*(\d+\.?\d*)%", resultado)

        positivos = float(porcentajes_match.group(1)) if porcentajes_match else "-"
        negativos = float(porcentajes_match.group(2)) if porcentajes_match else "-"
        neutros = float(porcentajes_match.group(3)) if porcentajes_match else "-"


        # Agregamos una fila a nuestra lista de datos, incluyendo el resumen completo
        resultado_escapado = resultado.replace('"', '""').replace('\n', ' ')

        # Extraer el resumen externo con regex
        resumen_externo_match = re.search(r"(?i)Resumen de comentarios sin sesgos.*?:?\s*(.+?)Temáticas más comentadas", resultado, re.DOTALL)
        resumen_externo = resumen_externo_match.group(1).strip() if resumen_externo_match else ""

        data.append({
            "APIES": apies,
            "RESUMEN EXTERNO": resumen_externo,
            "RESUMEN": resultado_escapado,
            "ATENCION AL CLIENTE": a_score,
            "TIEMPO DE ESPERA": t_score,
            "SANITARIOS": s_score,
            "POSITIVOS": positivos,
            "NEGATIVOS": negativos,
            "NEUTROS": neutros
        })

    logger.info("11 - Creando dataframe...")
    # Crear un DataFrame con los resultados
    df_resultados = pd.DataFrame(data)

    logger.info("12 - Creando archivo CSV")
    output = BytesIO()
    df_resultados.to_csv(output, index=False, encoding='utf-8', sep=',', quotechar='"', quoting=1)  # Guardamos como CSV

    # Volver al inicio del archivo para que Flask pueda leerlo
    output.seek(0)

    logger.info("13 - Transformando a Binario...")
    # Obtener los datos binarios
    archivo_binario = output.read()

    logger.info("14 - Eliminando posibles registros anteriores...")
    # Eliminar el registro anterior si existe
    archivo_anterior = AllApiesResumes.query.first()
    if archivo_anterior:
        db.session.delete(archivo_anterior)
        db.session.commit()

    logger.info("15 - Guardando en database.")
    # Crear una instancia del modelo y guardar el archivo binario en la base de datos
    archivo_resumido = AllApiesResumes(archivo_binario=archivo_binario)
    db.session.add(archivo_resumido)
    db.session.commit()

    logger.info("16 - Tabla lista y guardada. Proceso finalizado.")
    # Finalizar la función
    return

#----------------UTILS PARA SURVEY------------------------///////////////////////

def obtener_y_guardar_survey():

    # Paso 1: Leer keys del .env
    api_key = os.getenv('SURVEYMONKEY_API_KEY')
    access_token = os.getenv('SURVEYMONKEY_ACCESS_TOKEN')
    survey_id = os.getenv('SURVEY_ID')
    
    logger.info("2 - Ya en Utils - Iniciando la recuperación de la encuesta...")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    HOST = "https://api.surveymonkey.com"
    SURVEY_RESPONSES_ENDPOINT = f"/v3/surveys/{survey_id}/responses/bulk"
    SURVEY_DETAILS_ENDPOINT = f"/v3/surveys/{survey_id}/details"

    # Paso 2: Obtener detalles de la encuesta
    hora_inicio = datetime.now()
    logger.info("3 - Obteniendo detalles de la encuesta...")



    survey_details = requests.get(f"{HOST}{SURVEY_DETAILS_ENDPOINT}", headers=headers).json()

    # Crear mapas para preguntas y respuestas
    choice_map = {}
    question_map = {}
    for page in survey_details["pages"]:
        for question in page["questions"]:
            question_map[question["id"]] = question["headings"][0]["heading"]
            if "answers" in question:
                for answer in question["answers"]["choices"]:
                    choice_map[answer["id"]] = answer["text"]

    # Paso 3: Obtener las respuestas
    logger.info("4 - Obteniendo respuestas de la encuesta...")
    page = 1
    per_page = 10000
    all_responses = []

    while True:
        response_data = requests.get(f"{HOST}{SURVEY_RESPONSES_ENDPOINT}?page={page}&per_page={per_page}", headers=headers)
        if response_data.status_code == 200:
            responses_json = response_data.json()["data"]
            if not responses_json:
                break
            all_responses.extend(responses_json)
            page += 1
        else:
            logger.error(f"Error al obtener respuestas: {response_data.status_code}")
            break

    # Paso 4: Procesar respuestas y generar DataFrame
    logger.info("5 - Procesando respuestas...")
    responses_dict = {}

    for response in all_responses:
        respondent_id = response["id"]
        if respondent_id not in responses_dict:
            responses_dict[respondent_id] = {}

        responses_dict[respondent_id]['custom_variables'] = response.get('custom_variables', {}).get('ID_CODE', '')
        responses_dict[respondent_id]['date_created'] = response.get('date_created', '')[:10]
        for page in response["pages"]:
            for question in page["questions"]:
                question_id = question["id"]
                for answer in question["answers"]:
                    if "choice_id" in answer:
                        responses_dict[respondent_id][question_id] = choice_map.get(answer["choice_id"], answer["choice_id"])
                    elif "text" in answer:
                        responses_dict[respondent_id][question_id] = answer["text"]
                    elif "row_id" in answer and "text" in answer:
                        responses_dict[respondent_id][question_id] = answer["text"]

    df_responses = pd.DataFrame.from_dict(responses_dict, orient='index')
    all_responses = []


    # Paso 5: Limpiar columnas con tags HTML
    def extract_text_from_span(html_text):
        return re.sub(r'<[^>]*>', '', html_text)

    if '152421787' in df_responses.columns:
        df_responses['152421787'] = df_responses['152421787'].apply(extract_text_from_span)

    df_responses.rename(columns=question_map, inplace=True)
    df_responses.columns = [extract_text_from_span(col) for col in df_responses.columns]

    logger.info(f"6 - DataFrame con {df_responses.shape[0]} filas y {df_responses.shape[1]} columnas.")


    # Convertir el DataFrame a binario
    logger.info("7 - Convirtiendo DataFrame a binario...")
    #-----------------------Si no funciona vuelvo a habilitar esto>>>
    # output = BytesIO()
    # # df_responses.to_parquet(output, index=False)
    # df_responses.to_pickle(output)  # Cambiamos a pickle
    # binary_data = output.getvalue()
    #-----------------------------------------------------------------
    with BytesIO() as output:
        df_responses.to_pickle(output)  # Cambiamos a pickle
        binary_data = output.getvalue()


    # Paso 6: Guardar en la base de datos
    logger.info("8 - Guardando resultados en la base de datos...")

    # Primero, eliminar cualquier registro anterior
    db.session.query(Survey).delete()
    db.session.flush()
    
    # Crear un nuevo registro
    new_survey = Survey(data=binary_data)
    db.session.add(new_survey)
    db.session.commit()

    logger.info("9 - Datos guardados correctamente.")

    # Captura la hora de finalización
    hora_descarga_finalizada = datetime.now()

    # Calcula el intervalo de tiempo
    elapsed_time = hora_descarga_finalizada - hora_inicio
    elapsed_time_str = str(elapsed_time)
    logger.info(f"10 - Survey recuperado y guardado en db. Tiempo transcurrido de descarga y guardado: {elapsed_time_str}")

    #limpieza
    gc.collect()
    
    return  # Fin de la ejecución en segundo plano


# GET ONE FROM TOTAL RESUMEN OF COMMENTS --------------------------------------------/////


def get_resumes_for_apies(apies_input, db_data):
    logger.info("3 - Ejecutando util get_resumes_for_apies...")
    
    # Leer el archivo Excel desde la DB (binario)
    logger.info("4 - Recuperando excel desde binario...")
    binary_data = BytesIO(db_data)
    df = pd.read_pickle(binary_data)

    apies_input = int(apies_input)

    logger.info("5 - Filtrando comentarios correspondientes a la estación de servicio...")
    # Filtrar los comentarios correspondientes al número de APIES
    comentarios_filtrados = df[df.iloc[:, 1] == apies_input].iloc[:, 2]

    if comentarios_filtrados.empty:
        return f"No se encontraron comentarios para la estación {apies_input}"

    # Crear el prompt de OpenAI con los comentarios filtrados
    prompt = f"""
        A continuación, tienes una lista de comentarios de clientes sobre la estación de servicio {str(apies_input)}. Necesito que realices un resumen **sin sesgos** de los comentarios y respondas las siguientes indicaciones:

        1. **Resumen de comentarios sin sesgos**: Proporciona un análisis claro de los comentarios de los clientes. Si se mencionan nombres, citarlos en la respuesta con el motivo.
        
        2. **Temáticas más comentadas**:  Mostrar porcentaje de cada temática mencionada sobre la totalidad. Ordena las temáticas desde la más comentada hasta la menos comentada, identificando las quejas o comentarios más recurrentes. Si se mencionan nombres, citarlos en la respuesta con el motivo.

        3. **Motivos del malestar o quejas**:  Enfócate en el **motivo** que genera el malestar o la queja, no en la queja en sí. Mostrar porcentaje de comentarios de cada motivo de queja sobre la totalidad de los comentarios.  Si se mencionan nombres, citarlos en la respuesta con el motivo.

        4. **Puntaje de tópicos mencionados**: Si se mencionan algunos de los siguientes tópicos, proporciona un puntaje del 1 al 10 basado en el porcentaje de comentarios positivos sobre la totalidad de comentarios en cada uno. Si no hay comentarios sobre un tópico, simplemente coloca "-".
        
        - **A** (Atención al cliente)
        - **T** (Tiempo de espera)
        - **S** (Sanitarios)

        El puntaje se determina de la siguiente forma:
        - Si entre 90% y 99% de los comentarios totales de uno de los 3 tópicos son positivos, el puntaje es 9, en el tópico correspondiente.
        - Si el 100% de los comentarios totales  de uno de los 3 tópicos son positivos, el puntaje es 10, en el tópico correspondiente.
        - Si entre 80% y el 89% de los comentarios totales de uno de los 3 tópicos son positivos, el puntaje es 8, en el tópico correspondiente. y así sucesivamente.

        **Esta es la lista de comentarios para el análisis:**
        {comentarios_filtrados.tolist()}

        **Proporción y puntaje para cada tópico mencionado:**
        1. Atención al cliente (A): \[Porcentaje de comentarios positivos\] — Puntaje del 1 al 10.
        2. Tiempo de espera (T): \[Porcentaje de comentarios positivos\] — Puntaje del 1 al 10.
        3. Sanitarios (S): \[Porcentaje de comentarios positivos\] — Puntaje del 1 al 10.

        **Código Resumen**:

        ##APIES {str(apies_input)}-A:5,T:Y,S:8## ( los puntajes son meramente demostrativos para entender el formato que espero de la respuesta )
        """
    logger.info("6 - Pidiendo resumen a OPENAI...")
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un analista que clasifica comentarios sobre eficiencia."},
                {"role": "user", "content": prompt}
            ]
        )
        resumen = completion.choices[0].message.content

    except Exception as e:
        return f"Error al procesar el APIES {apies_input}: {e}"

    logger.info("7 - Extracción de datos importantes del texto resultante...")
    # Extraer puntajes usando regex
    a_match = re.search(r"A:(\d+)", resumen)
    t_match = re.search(r"T:(\d+)", resumen)
    s_match = re.search(r"S:(\d+)", resumen)

    a_score = int(a_match.group(1)) if a_match else "-"
    t_score = int(t_match.group(1)) if t_match else "-"
    s_score = int(s_match.group(1)) if s_match else "-"

    # Preparar datos para el Excel
    logger.info("8 - Preparando matriz para crear el excel de respuesta...")
    data = [{
        "APIES": apies_input,
        "ATENCION AL CLIENTE": a_score,
        "TIEMPO DE ESPERA": t_score,
        "SANITARIOS": s_score,
        "RESUMEN": resumen
    }]

    df_resultados = pd.DataFrame(data)
    logger.info("9 - Creando excel...")
    # Crear un archivo Excel en memoria
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_resultados.to_excel(writer, index=False, sheet_name='Resúmenes')

    output.seek(0)
    logger.info("10 - Devolviendo excel a la ruta...")
    return output  # Devuelve el archivo Excel


# GET EVALUATIONS OF ALL - EL QUE AGARRA EL BBDD CONCAT Y A CADA COMENTARIO LE HACE UNA EVALUACIÓN>>>>>



def get_evaluations_of_all(file_content):
    try:
        logger.info("4 - Util get_evaluations_of_all inicializado")
        # Leer el archivo Excel desde el contenido en memoria (file_content)
        logger.info("5 - Leyendo excel y transformando fechas...")
        df = pd.read_excel(BytesIO(file_content))

        # Verificar que las columnas necesarias existan
        if 'COMENTARIO' not in df.columns or 'APIES' not in df.columns:
            logger.error("El archivo no contiene las columnas necesarias: 'COMENTARIO' y 'APIES'")
            return

        # Convertir la columna de fechas a tipo datetime
        df['FECHA'] = pd.to_datetime(df['FECHA'], format='%d/%m/%Y')
        df['FECHA'] = df['FECHA'].dt.date

        # Filtrar los comentarios entre el primer y el último día del mes pasado
        logger.info("6 - Filtrando comentarios por fecha (solo aparecen las del último mes cerrado)...")
        hoy = datetime.today()
        primer_dia_mes_actual = hoy.replace(day=1)
        primer_dia_mes_pasado = primer_dia_mes_actual - pd.DateOffset(months=1)
        ultimo_dia_mes_pasado = primer_dia_mes_actual - timedelta(days=1)

        logger.info(f"Primer día del mes pasado: {primer_dia_mes_pasado}")
        logger.info(f"Último día del mes pasado: {ultimo_dia_mes_pasado}")
        logger.info(f"Fechas únicas en el archivo: {df['FECHA'].unique()}")

        df_filtrado = df[(df['FECHA'] >= primer_dia_mes_pasado.date()) & (df['FECHA'] <= ultimo_dia_mes_pasado.date())]

        logger.info(f"Comentarios filtrados: {len(df_filtrado)}")

        # Evaluar cada comentario con OpenAI y agregar columna 'SENTIMIENTO'
        logger.info("7 - Evaluando comentarios con OpenAI...")
        for idx, row in df_filtrado.iterrows():
            comentario = row['COMENTARIO']
            apies = row['APIES']
            prompt = f"Clasifica el siguiente comentario como 'positivo', 'negativo' o 'no clasificable'. Si es 'no clasificable', no incluyas las palabras 'positivo' o 'negativo' en tu respuesta: {comentario}"

            try:
                logger.info(f"El prompt para el comentario {idx} está en proceso...")
                completion = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Eres un analista que clasifica comentarios segun el sentimiento de los clientes."},
                        {"role": "user", "content": prompt}
                    ]
                )

                resumen = completion.choices[0].message.content.lower()

                if "positivo" in resumen:
                    df_filtrado.at[idx, 'SENTIMIENTO'] = "positivo"
                elif "negativo" in resumen:
                    df_filtrado.at[idx, 'SENTIMIENTO'] = "negativo"
                else:
                    df_filtrado.at[idx, 'SENTIMIENTO'] = "-"

            except Exception as e:
                logger.info(f"Error al procesar el comentario {idx}, {str(e)}")
                df_filtrado.at[idx, 'SENTIMIENTO'] = "-"

        # Guardar el DataFrame actualizado en formato binario
        logger.info("11 - Creando dataframe actualizado con sentimiento...")
        output = BytesIO()
        df_filtrado.to_csv(output, index=False, encoding='utf-8', sep=',', quotechar='"', quoting=1)
        output.seek(0)
        archivo_binario = output.read()

        # Cerrar el BytesIO
        output.close()

        logger.info("14 - Eliminando posibles registros anteriores...")
        archivo_anterior = AllCommentsWithEvaluation.query.first()
        if archivo_anterior:
            db.session.delete(archivo_anterior)
            db.session.commit()

        logger.info("15 - Guardando en database.")
        archivo_resumido = AllCommentsWithEvaluation(archivo_binario=archivo_binario)
        db.session.add(archivo_resumido)
        db.session.commit()

        logger.info("16 - Tabla lista y guardada. Proceso finalizado.")
        return

    except Exception as e:
        logger.error(f"Error en el proceso general: {str(e)}")
        return
