from flask import Blueprint, send_file, make_response, request, jsonify, render_template, current_app # Blueprint para modularizar y relacionar con app
from flask_bcrypt import Bcrypt                                  # Bcrypt para encriptación
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity   # Jwt para tokens
from models import User, Survey, TotalComents                    # importar tabla "User" de models
from database import db                                          # importa la db desde database.py
from datetime import timedelta, datetime                         # importa tiempo especifico para rendimiento de token válido
from utils import get_resumes_for_apies, obtener_y_guardar_survey, get_resumes, exportar_reporte_json, exportar_y_guardar_reporte, obtener_reporte, iniciar_sesion_y_obtener_sesskey, compilar_reportes_existentes
from logging_config import logger
import os                                                        # Para datos .env
from dotenv import load_dotenv                                   # Para datos .env
load_dotenv()
import pytz
import re
import pandas as pd
from io import BytesIO



admin_bp = Blueprint('admin', __name__)     # instanciar admin_bp desde clase Blueprint para crear las rutas.
bcrypt = Bcrypt()
jwt = JWTManager()

# Sistema de key base pre rutas ------------------------:

API_KEY = os.getenv('API_KEY')

def check_api_key(api_key):
    return api_key == API_KEY

@admin_bp.before_request
def authorize():
    if request.method == 'OPTIONS':
        return
    if request.path in ['/','/descargar_excel','/create_resumes', '/reportes_disponibles', '/create_user', '/login', '/users','/update_profile','/update_profile_image','/update_admin']:
        return
    api_key = request.headers.get('Authorization')
    if not api_key or not check_api_key(api_key):
        return jsonify({'message': 'Unauthorized'}), 401
    
#--------------------------------RUTAS SINGLE---------------------------------

# Ruta de prueba time-out-test------------------------------------------------
@admin_bp.route('/test', methods=['GET'])
def test():
    return jsonify({'message': 'test bien sucedido','status':"Si lees esto, tenemos que ver como manejar el timeout porque los archivos llegan..."}),200

# RUTA DOCUMENTACION
@admin_bp.route('/', methods=['GET'])
def show_hello_world():
         return render_template('instructions.html')

# RUTA REPORTES DISPONIBLES CON DATOS-----------------------------------------
@admin_bp.route('/reportes_disponibles', methods=['GET'])
def reportes_disponibles():
    lista_reportes = compilar_reportes_existentes()
    return jsonify({
        'lista_reportes_disponibles': lista_reportes['disponibles'],
        'total_disponibles': len(lista_reportes['disponibles']),
        'lista_reportes_no_disponibles': lista_reportes['no_disponibles'],
        'total_no_disponibles': len(lista_reportes['no_disponibles']),
        'result': 'ok'
    }), 200

# Ruta para Obtener USUARIOS POR ASIGNACIÓN PARA GESTORES ( sin parámetros )
@admin_bp.route('/usuarios_por_asignacion_para_gestores', methods=['POST'])
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
    
# Ruta 2 para obtener usuarios por asignacion para gestores ( via params )
@admin_bp.route('/usuarios_por_asignacion_para_gestores_v2', methods=['GET'])
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

@admin_bp.route('/recuperar_reporte', methods=['POST'])
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

    
    

@admin_bp.route('/obtener_reporte', methods=['POST'])
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


# RUTAS SURVEY NUEVAS ( PEDIDO Y RECUPERACION )-------------------------------------------------------------//////////////////////////
@admin_bp.route('/recuperar_survey', methods=['GET'])
def obtener_y_guardar_survey_ruta():
    from extensions import executor
    logger.info("0 - GET > /recuperar_survey a comenzando...")

    
    
# Lanzar la función de exportar y guardar reporte en un job separado
    executor.submit(run_obtener_y_guardar_survey)

    logger.info(f"1 - Hilo de ejecución independiente inicializado, retornando 200...")

    return jsonify({"message": "El proceso de recuperacion de survey ha comenzado"}), 200

def run_obtener_y_guardar_survey():
    with current_app.app_context():
        obtener_y_guardar_survey()

    

@admin_bp.route('/descargar_survey', methods=['GET'])
def descargar_survey():
    try:
        # Obtener el registro más reciente de la base de datos
        survey_record = Survey.query.order_by(Survey.id.desc()).first()

        if not survey_record:
            return jsonify({"message": "No se encontraron encuestas en la base de datos"}), 404

        # Convertir los datos binarios de vuelta a DataFrame
        logger.info("Recuperando archivo binario desde la base de datos...")
        binary_data = survey_record.data
        df_responses = pd.read_pickle(BytesIO(binary_data))

        # Convertir DataFrame a Excel en memoria
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_responses.to_excel(writer, index=False, sheet_name='Sheet1')

        # Preparar el archivo Excel para enviarlo
        output.seek(0)
        logger.info("Archivo Excel creado y listo para descargar.")

        return send_file(output, download_name='survey_respuestas.xlsx', as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        logger.error(f"Error al generar el archivo Excel: {str(e)}")
        return jsonify({"message": "Hubo un error al generar el archivo Excel"}), 500


# ----------------------------------------------------------------------------------------------------------//////////////////////////


# RUTA CREAR USUARIO
@admin_bp.route('/create_user', methods=['POST'])
def create_user():
    try:
        email = request.json.get('email')
        password = request.json.get('password')
        name = request.json.get('name')
        dni = request.json.get('dni')
        admin = False
        url_image = "base"
        # Después de crear el primer administrador y la consola de agregar y quitar admins borrar este pedazo:

        #-----------------------------------------------------------------------------------------------------
        if not email or not password or not name or not dni:
            return jsonify({'error': 'Email, password, dni and Name are required.'}), 400

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({'error': 'Email already exists.'}), 409

        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')


        # Ensamblamos el usuario nuevo
        new_user = User(email=email, password=password_hash, name=name , dni=dni, admin=admin, url_image= url_image)

        db.session.add(new_user)
        db.session.commit()

        good_to_share_to_user = {
            'name':new_user.name,
            'email':new_user.email,
            'dni':new_user.dni,
            'admin':new_user.admin,
            'url_image':new_user.url_image
        }

        return jsonify({'message': 'User created successfully.','user_created':good_to_share_to_user}), 201

    except Exception as e:
        return jsonify({'error': 'Error in user creation: ' + str(e)}), 500


#RUTA LOG-IN ( CON TOKEN DE RESPUESTA )
@admin_bp.route('/login', methods=['POST'])
def get_token():
    try:
        #  Primero chequeamos que por el body venga la info necesaria:
        email = request.json.get('email')
        password = request.json.get('password')

        if not email or not password:
            return jsonify({'error': 'Email y password son requeridos.'}), 400
        
        # Buscamos al usuario con ese correo electronico ( si lo encuentra lo guarda ):
        login_user = User.query.filter_by(email=request.json['email']).one()

        # Verificamos que el password sea correcto:
        password_from_db = login_user.password #  Si loguin_user está vacio, da error y se va al "Except".
        true_o_false = bcrypt.check_password_hash(password_from_db, password)
        
        # Si es verdadero generamos un token y lo devuelve en una respuesta JSON:
        if true_o_false:
            expires = timedelta(minutes=30)  # pueden ser "hours", "minutes", "days","seconds"

            user_dni = login_user.dni       # recuperamos el id del usuario para crear el token...
            access_token = create_access_token(identity=user_dni, expires_delta=expires)   # creamos el token con tiempo vencimiento
            return jsonify({ 'access_token':access_token, 'name':login_user.name, 'admin':login_user.admin, 'dni':user_dni, 'email':login_user.email, 'url_image':login_user.url_image}), 200  # Enviamos el token al front ( si es necesario serializamos el "login_user" y tambien lo enviamos en el objeto json )

        else:
            return {"Error":"Contraseña  incorrecta"}
    
    except Exception as e:
        return {"Error":"El email proporcionado no corresponde a ninguno registrado: " + str(e)}, 500
    
# EJEMPLO DE RUTA RESTRINGIDA POR TOKEN. ( LA MISMA RECUPERA TODOS LOS USERS Y LO ENVIA PARA QUIEN ESTÉ LOGUEADO )
    

@admin_bp.route('/users')
@jwt_required()  # Decorador para requerir autenticación con JWT
def show_users():
    current_user_dni = get_jwt_identity()  # Obtiene la id del usuario del token
    if current_user_dni:
        users = User.query.all()
        user_list = []
        for user in users:
            user_dict = {
                'dni': user.dni,
                'email': user.email,
                'name': user.name,
                'admin': user.admin,
                'url_image': user.url_image
            }
            user_list.append(user_dict)
        return jsonify({"lista_usuarios":user_list , 'cantidad':len(user_list)}), 200
    else:
        return {"Error": "Token inválido o vencido"}, 401


@admin_bp.route('/update_profile', methods=['PUT'])
def update():
    email = request.json.get('email')
    password = request.json.get('password')
    name = request.json.get('name')
    dni = request.json.get('dni')
    url_image = "base"


    # Verificar que todos los campos requeridos estén presentes
    if not email or not password or not name or not dni or not url_image:
        return jsonify({"error": "Todos los campos son obligatorios"}), 400

    # Buscar al usuario por email
    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    # Actualizar los datos del usuario
    user.name = name
    user.dni = dni
    user.password = bcrypt.generate_password_hash(password)  # Asegúrate de hash la contraseña antes de guardarla
    user.url_image = url_image

    try:
        db.session.commit()
        return jsonify({"message": "Usuario actualizado con éxito"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar el usuario: {str(e)}"}), 500
    


@admin_bp.route('/update_profile_image', methods=['PUT'])
def update_profile_image():
    email = request.json.get('email')
    url_image = request.json.get('url_image')

    # Verificar que ambos campos estén presentes
    if not email or not url_image:
        return jsonify({"error": "El email y la URL de la imagen son obligatorios"}), 400

    # Buscar al usuario por email
    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    # Actualizar solo la URL de la imagen
    user.url_image = url_image

    try:
        db.session.commit()
        return jsonify({"message": "Imagen de perfil actualizada con éxito"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar la imagen: {str(e)}"}), 500
    

@admin_bp.route('/update_admin', methods=['PUT'])
def update_admin():
    email = request.json.get('email')
    admin = request.json.get('admin')

    # Verificar que ambos campos estén presentes
    if email is None or admin is None:
        return jsonify({"error": "El email y la situación admin son obligatorios"}), 400

    # Buscar al usuario por email
    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    # Actualizar estado admin
    user.admin = not user.admin

    try:
        db.session.commit()
        return jsonify({"message": f"Estado admin de {email} ahora es {'admin' if user.admin else 'no admin'}", "admin": user.admin}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar el estado admin: {str(e)}"}), 500
    

@admin_bp.route('/get_user/<int:dni>', methods=['GET'])
def get_user(dni):
    try:
        
        login_user = User.query.filter_by(dni=dni).one()

        if login_user:
            return jsonify({'name':login_user.name, 'admin':login_user.admin, 'dni':login_user.dni, 'email':login_user.email, 'url_image':login_user.url_image}), 200 

        else:
            return {"Error":"No se encontró un usuario con ese documento"}
    
    except Exception as e:
        return {"Error":"El dni proporcionado no corresponde a ninguno registrado: " + str(e)}, 500
    

    #-----------------------------RUTAS PARA EXPERIENCIA APIES-------------------


@admin_bp.route('/create_resumes', methods=['POST'])
def create_resumes():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No se encontró ningún archivo en la solicitud"}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({"error": "No se seleccionó ningún archivo"}), 400

        if file and file.filename.lower().endswith('.xlsx'):
            # Leer el archivo directamente desde la memoria
            file_content = file.read()

            # Llamamos al util que procesa el contenido del archivo y genera el archivo Excel
            output = get_resumes(file_content)

            # Preparar la respuesta para enviar el archivo Excel
            return send_file(output, download_name="resumenes.xlsx", as_attachment=True)

        else:
            return jsonify({"error": "El archivo no es válido. Solo se permiten archivos .xlsx"}), 400
    
    except Exception as e:
        return jsonify({"error": f"Se produjo un error: {str(e)}"}), 500
    

# ------------------------RESUMEN GIGANTE DE COMENTARIOS DE APIES-----------------------------------/////////////////////////////////////////////////////////

@admin_bp.route('/eliminar_excel_total', methods=['DELETE'])
def eliminar_excel():
    try:
        excel_data = TotalComents.query.first()
        if excel_data:
            db.session.delete(excel_data)
            db.session.commit()
            return jsonify({"message": "Excel eliminado con éxito"}), 200
        else:
            return jsonify({"message": "No hay archivo Excel para eliminar"}), 404
    except Exception as e:
        return jsonify({"message": "Error al eliminar el archivo"}), 500
    

@admin_bp.route('/subir_excel_total', methods=['POST'])
def subir_excel():
    try:
        # Eliminar el registro anterior
        excel_data = TotalComents.query.first()
        if excel_data:
            db.session.delete(excel_data)
            db.session.commit()

        # Guardar el nuevo Excel en binario
        file = request.files['file']
        df = pd.read_excel(file)  # Cargamos el Excel usando pandas
        binary_data = BytesIO()
        df.to_pickle(binary_data)  # Convertimos el DataFrame a binario
        binary_data.seek(0)

        nuevo_excel = TotalComents(data=binary_data.read())
        db.session.add(nuevo_excel)
        db.session.commit()

        return jsonify({"message": "Archivo subido con éxito"}), 200
    except Exception as e:
        return jsonify({"message": f"Error al subir el archivo: {str(e)}"}), 500
    
@admin_bp.route('/descargar_excel', methods=['GET'])
def descargar_excel():
    try:
        logger.info("1 - Entró en la ruta descargar_excel")
        # Obtener el registro más reciente de la base de datos
        excel_data = TotalComents.query.first()

        if not excel_data:
            return jsonify({"message": "No se encontró ningún archivo Excel en la base de datos"}), 404

        logger.info("2 - Encontró el excel en db, traduciendo de binario a dataframe..")
        # Convertir los datos binarios de vuelta a DataFrame
        binary_data = BytesIO(excel_data.data)
        df = pd.read_pickle(binary_data)

        logger.info("3 - De dataframe a excel...")
        # Convertir el DataFrame a un archivo Excel en memoria
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='APIES_Data')

        output.seek(0)  # Mover el puntero al inicio del archivo

        # Enviar el archivo Excel como respuesta
        return send_file(output, 
                         download_name='apies_data.xlsx', 
                         as_attachment=True, 
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        return jsonify({"message": f"Error al descargar el archivo: {str(e)}"}), 500
    

@admin_bp.route('/existencia_excel', methods=['GET'])
def existencia_excel():
    try:
        # Obtener el registro más reciente de la base de datos
        excel_data = TotalComents.query.first()

        if not excel_data:
            return jsonify({"message": "No se encontró ningún archivo Excel en la base de datos", "ok": False}), 404
        else:
            # Formatear el timestamp de manera legible (dd/mm/yyyy HH:MM:SS)
            datetime = excel_data.timestamp.strftime('%d/%m/%Y %H:%M:%S')
            return jsonify({"message": f"El archivo se encuentra disponible. Y data del día: {datetime}", "ok": True, "datetime":datetime}), 200
        
    except Exception as e:
        return jsonify({"message": f"Error al confirmar la existencia del archivo: {str(e)}", "ok": False}), 500

@admin_bp.route('/get_one_resume', methods=['POST'])
def get_one_resume():
    logger.info("1 - Entró en ruta /get_one_resume...")
    request_data = request.json
    apies_input = request_data.get("apies")
    logger.info(f"2 - Recuperando apies: {apies_input}")


    db_data = TotalComents.query.first().data

    if not db_data:
        return jsonify({"error": "No se encontraron datos en la base de datos"}), 404

    # Ahora pasamos los datos binarios al util
    output = get_resumes_for_apies(apies_input, db_data)

    # Aquí verificamos si `output` contiene un mensaje de error en lugar de un archivo
    if isinstance(output, str) and "No se encontraron comentarios" in output:
        logger.info(output)
        return jsonify({"error": output}), 404

    logger.info(f"11 - Devolviendo resultado de apies: {apies_input}. Fin de la ejecución.")
    # Devolver el Excel al frontend si todo va bien
    return send_file(output, download_name=f"resumen_apies_{apies_input}.xlsx", as_attachment=True)