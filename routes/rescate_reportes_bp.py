from flask import Blueprint, send_file, make_response, request, jsonify, render_template, current_app, Response # Blueprint para modularizar y relacionar con app
from flask_bcrypt import Bcrypt                                  # Bcrypt para encriptación
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity   # Jwt para tokens
from database import db                                          # importa la db desde database.py
from datetime import timedelta, datetime                         # importa tiempo especifico para rendimiento de token válido
from utils.rescate_utils import exportar_reporte_json, exportar_y_guardar_reporte, obtener_reporte, iniciar_sesion_y_obtener_sesskey, compilar_reportes_existentes
from logging_config import logger
import os                                                        # Para datos .env
from models import Reporte
from dotenv import load_dotenv                                   # Para datos .env
load_dotenv()
import pytz
import re
import pandas as pd
from io import BytesIO
import io



rescate_reportes_bp = Blueprint('rescate_reportes_bp', __name__)     # instanciar admin_bp desde clase Blueprint para crear las rutas.
bcrypt = Bcrypt()
jwt = JWTManager()

# Sistema de key base pre rutas ------------------------:

API_KEY = os.getenv('API_KEY')

def check_api_key(api_key):
    return api_key == API_KEY


@rescate_reportes_bp.before_request
def authorize():
    if request.method == 'OPTIONS':
        return
    if request.path in ['/test_rescate_reportes_bp','/','/correccion_campos_vacios','/descargar_positividad_corregida','/download_comments_evaluation','/all_comments_evaluation','/download_resume_csv','/create_resumes_of_all','/descargar_excel','/create_resumes', '/reportes_disponibles', '/create_user', '/login', '/users','/update_profile','/update_profile_image','/update_admin']:
        return
    api_key = request.headers.get('Authorization')
    if not api_key or not check_api_key(api_key):
        return jsonify({'message': 'Unauthorized'}), 401
    
# RUTA TEST:

@rescate_reportes_bp.route('/test_rescate_reportes_bp', methods=['GET'])
def test():
    return jsonify({'message': 'test bien sucedido','status':"Si lees esto, tenemos que ver como manejar el timeout porque los archivos llegan..."}),200



# RUTA REPORTES DISPONIBLES CON DATOS-----------------------------------------
@rescate_reportes_bp.route('/reportes_disponibles', methods=['GET'])
def reportes_disponibles():
    lista_reportes = compilar_reportes_existentes()
    return jsonify({
        'lista_reportes_disponibles': lista_reportes['disponibles'],
        'total_disponibles': len(lista_reportes['disponibles']),
        'lista_reportes_no_disponibles': lista_reportes['no_disponibles'],
        'total_no_disponibles': len(lista_reportes['no_disponibles']),
        'result': 'ok'
    }), 200

# DEPRECADO  Ruta para Obtener USUARIOS POR ASIGNACIÓN PARA GESTORES ( sin parámetros ) - DEPRECADO / QUIERE OBTENER DE UNA TIRADA.
@rescate_reportes_bp.route('/usuarios_por_asignacion_para_gestores', methods=['POST'])
def exportar_reporte():
    print("funciona la ruta")
    data = request.get_json()
    if 'username' not in data or 'password' not in data or 'url' not in data:
        return jsonify({"error": "Falta username,password o url en el cuerpo JSON"}), 400
    username = data['username']
    password = data['password']
    url = data['url']

    # Llamas a la función de utils para exportar el reporte a Html
    json_file = exportar_reporte_json(username, password, url)
    if json_file:
        print("Compilando paquete response con json dentro...")
        response = make_response(json_file)
        response.headers['Content-Type'] = 'application/json'
        print("Devolviendo JSON - log final")
        return response, 200
    else:
        return jsonify({"error": "Error al obtener el reporte en HTML, log final error"}), 500
    
# DEPRECADO  Ruta 2 para obtener usuarios por asignacion para gestores ( via params )  - DEPRECADO / QUIERE OBTENER DE UNA TIRADA.
@rescate_reportes_bp.route('/usuarios_por_asignacion_para_gestores_v2', methods=['GET'])
def exportar_reporte_v2():
    username = request.args.get('username')
    password = request.args.get('password')
    url = request.args.get('url')

    if not username or not password or not url:
        return jsonify({"error": "Falta username o password en los parámetros de la URL"}), 400

    print("los datos username y password fueron recuperados OK, se va a ejecutar la funcion de utils ahora...")

    json_file = exportar_reporte_json(username, password, url)
    if json_file:
        print("Compilando paquete response con json dentro...")
        response = make_response(json_file)
        response.headers['Content-Type'] = 'application/json'
        print("Devolviendo JSON - log final")
        return response, 200
    else:
        return jsonify({"error": "Error al obtener el reporte en HTML, log final error"}), 500

# --------------------------------------------------------------------------------

#--------------------------------RUTAS MULTIPLES-----------------------------------------------------------------------------------

#RECUPERAR DE FUENTE>
@rescate_reportes_bp.route('/recuperar_reporte', methods=['POST'])
def exportar_y_guardar_reporte_ruta():
    from extensions import executor
    logger.info("POST > /recuperar_reporte comenzando...")

    data = request.get_json()
    if 'username' not in data or 'password' not in data or 'url' not in data:
        return jsonify({"error": "Falta username, password, url o user_id en el cuerpo JSON"}), 400
    logger.info(f"1 - Url requerida: {data['url']}.")
    username = data['username']
    password = data['password']
    url = data['url']

    # Llamando al inicio de session por separado y recuperando resultados...
    session, sesskey = iniciar_sesion_y_obtener_sesskey(username, password, url)
    if not session or not sesskey:
        logger.info("Error al iniciar sesión o al obtener el sesskey.")
        return jsonify({"error": "Error al iniciar sesión o al obtener el sesskey"}), 500
    
# Lanzar la función de exportar y guardar reporte en un job separado
    executor.submit(run_exportar_y_guardar_reporte, session, sesskey, username, url)

    return jsonify({"message": "El proceso de recuperacion del reporte ha comenzado"}), 200

def run_exportar_y_guardar_reporte(session, sesskey, username, url):
    with current_app.app_context():
        exportar_y_guardar_reporte(session, sesskey, username, url)

    
    

#DESCARGAR DE SERVIDOR PROPIO>
@rescate_reportes_bp.route('/obtener_reporte', methods=['POST'])
def descargar_reporte():
    logger.info("POST > /obtener_reporte comenzando...")
    logger.info("1 - Funciona la ruta de descarga")
    data = request.get_json()
    if 'reporte_url' not in data:
        return jsonify({"error": "Falta reporte_id, username o tipo de archivo en el cuerpo JSON"}), 400

    reporte_url = data['reporte_url']
    file_type = data.get('file_type', 'csv')
    zip_option = data.get('zip', 'no')
    logger.info(f"2 - Url requerida para descarga: {reporte_url}")
    
    reporte_data, created_at, title = obtener_reporte(reporte_url)
    if title is None:
        title = "reporte_obtenido"
    # -------------------------------------------------------------LIMPIEZA DE TITLE------------------------------------------
    logger.info("4 - Limpiando nombre de caracteres especiales para guardado...")
    # Reemplazar caracteres no válidos en nombres de archivos
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)

    # Reemplazar espacios y otros espacios en blanco por '_'
    safe_title = re.sub(r'\s+', '_', safe_title)
    # ------------------------------------------------------------------------------------------------------------------------
    logger.info("5 - Creando respuesta con archivo y enviando. Fin de la ejecución.")
    if reporte_data:
        # Formatear la fecha de creación
        local_tz = pytz.timezone('America/Argentina/Buenos_Aires')
        created_at_utc = created_at.replace(tzinfo=pytz.utc)  # Asignar la zona horaria UTC
        created_at_local = created_at_utc.astimezone(local_tz)  # Convertir a la zona horaria local
        timestamp = created_at_local.strftime('%d-%m-%Y_%H-%M')

        if file_type == 'xlsx':
            filename = f'{safe_title}_{timestamp}.xlsx'
            response = make_response(reporte_data)
            response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif file_type == 'json':
            filename = f'{safe_title}_{timestamp}.json'
            response = make_response(reporte_data)
            response.headers['Content-Type'] = 'application/json'
        elif file_type == 'html':
            filename = f'{safe_title}_{timestamp}.html'
            response = make_response(reporte_data)
            response.headers['Content-Type'] = 'text/html'
        elif file_type == 'csv':
            filename = f'{safe_title}_{timestamp}.csv'
            response = make_response(reporte_data)
            response.headers['Content-Type'] = 'text/csv'
        else:
            # Default to CSV if the file_type is unknown
            filename = f'{safe_title}_{timestamp}.csv'
            response = make_response(reporte_data)
            response.headers['Content-Type'] = 'text/csv'

        # Agrega el encabezado de Content-Disposition con el nombre del archivo
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'

        return response, 200
    else:
        logger.info("El util>obtener_reporte no devolvió la data...Respuesta de server 404")
        return jsonify({"error": "No se encontró el reporte"}), 404

# RESCATAR LISTA DE REPORTES EXISTENTES (PARA NUEVO FRONT)>--------------------------------


@rescate_reportes_bp.route('/reportes_acumulados', methods=['GET'])
def listar_reportes_agrupados():
    # Traemos todos los reportes ordenados primero por report_url y luego por fecha descendente
    reportes = Reporte.query.order_by(Reporte.report_url, Reporte.created_at.desc()).all()

    # Usamos un diccionario para agrupar por report_url
    grupos = {}
    for rep in reportes:
        rep_data = {
            "id": rep.id,
            "user_id": rep.user_id,
            "report_url": rep.report_url,
            "title": rep.title,
            "size_megabytes": rep.size,
            "elapsed_time": rep.elapsed_time,
            "created_at": rep.created_at.strftime("%d/%m/%Y %H:%M:%S") if rep.created_at else None
        }
        if rep.report_url not in grupos:
            grupos[rep.report_url] = []
        grupos[rep.report_url].append(rep_data)

    # Armamos el array de respuesta, donde cada objeto representa un grupo único
    resultado = []
    for url, versiones in grupos.items():
        resultado.append({
            "report_url": url,
            "version_count": len(versiones),
            "versions": versiones
        })

    return jsonify(resultado)


# Descargar reporte especifico por ID----------------------------------

@rescate_reportes_bp.route('/descargar_reporte/<int:report_id>', methods=['GET'])
def descargar_reporte_especifico(report_id):
    # Buscamos el reporte por id
    report = Reporte.query.get(report_id)
    if not report:
        return jsonify({'error': 'Reporte no encontrado'}), 404

    # Creamos un archivo en memoria con el contenido del reporte
    file_data = io.BytesIO(report.data)

    # Armamos un nombre de archivo: "titulo_fecha.csv"
    if report.created_at:
        timestamp = report.created_at.strftime("%Y%m%d_%H%M%S")
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{report.title}_{timestamp}.csv"

    # Mandamos el archivo como descarga, usando mimetype text/csv
    return send_file(
        file_data,
        as_attachment=True,
        download_name=filename,
        mimetype='text/csv'
    ),200