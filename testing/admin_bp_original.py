# En el conjunto de datos que quiero separar ( en este caso este tipo de rutas ), importo...
from flask import Blueprint,send_file, request, jsonify, render_template # Blueprint para modularizar y relacionar con app
from flask_bcrypt import Bcrypt                                  # Bcrypt para encriptación
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity   # Jwt para tokens
from models import User                                          # importar tabla "User" de models
from database import db                                          # importa la db desde database.py
from datetime import timedelta                                   # importa tiempo especifico para rendimiento de token válido
from routes.utils import exportar_reporte_excel


admin_bp = Blueprint('admin', __name__)     # instanciar admin_bp desde clase Blueprint para crear las rutas.

bcrypt = Bcrypt()
jwt = JWTManager()

# Ruta para Obtener USUARIOS POR ASIGNACIÓN PARA GESTORES ( sin parámetros )
@admin_bp.route('/usuarios_por_asignacion_para_gestores', methods=['POST'])
def exportar_reporte():
    print("funciona la ruta")
    data = request.get_json()
    if 'username' not in data or 'password' not in data:
        return jsonify({"error": "Falta username o password en el cuerpo JSON"}), 400
    username = data['username']
    password = data['password']

    # Llamas a la función de utils para exportar el reporte a Excel
    excel_file = exportar_reporte_excel(username, password)

    if excel_file:
        # Devolver el archivo de Excel como respuesta a la solicitud
        return send_file(excel_file, as_attachment=True, download_name='reporte_excel.xlsx')
    else:
        # Manejo de errores si no se pudo exportar el reporte
        return "Error al exportar el reporte a Excel", 500

    
# Ruta 2 para obtener usuarios por asignacion para gestores ( via params )
@admin_bp.route('/usuarios_por_asignacion_para_gestores_v2', methods=['GET'])
def exportar_reporte_v2():
    username = request.args.get('username')
    password = request.args.get('password')

    if not username or not password:
        return jsonify({"error": "Falta username o password en los parámetros de la URL"}), 400

    print("los datos username y password fueron recuperados OK, se va a ejecutar la funcion de utils ahora...")
    # Llamas a la función de utils para exportar el reporte a Excel
    excel_file = exportar_reporte_excel(username, password)

    if excel_file:
        print("excel_file existe y se está por devolver")
        # Devolver el archivo de Excel como respuesta a la solicitud
        return send_file(excel_file, as_attachment=True, download_name='reporte_excel.xlsx')
    else:
        # Manejo de errores si no se pudo exportar el reporte
        return "Error al exportar el reporte a Excel", 500



# RUTA DOCUMENTACION
@admin_bp.route('/', methods=['GET'])
def show_hello_world():
         return render_template('instructions.html')


# RUTA CREAR USUARIO
@admin_bp.route('/users', methods=['POST'])
def create_user():
    try:
        email = request.json.get('email')
        password = request.json.get('password')
        name = request.json.get('name')

        if not email or not password or not name:
            return jsonify({'error': 'Email, password and Name are required.'}), 400

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({'error': 'Email already exists.'}), 409

        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')


        # Ensamblamos el usuario nuevo
        new_user = User(email=email, password=password_hash, name=name)


        db.session.add(new_user)
        db.session.commit()

        good_to_share_user = {
            'id': new_user.id,
            'name':new_user.name,
            'email':new_user.email,
            'password':password
        }

        return jsonify({'message': 'User created successfully.','user_created':good_to_share_user}), 201

    except Exception as e:
        return jsonify({'error': 'Error in user creation: ' + str(e)}), 500


#RUTA LOG-IN ( CON TOKEN DE RESPUESTA )
@admin_bp.route('/token', methods=['POST'])
def get_token():
    try:
        #  Primero chequeamos que por el body venga la info necesaria:
        email = request.json.get('email')
        password = request.json.get('password')

        if not email or not password:
            return jsonify({'error': 'Email and password are required.'}), 400
        
        # Buscamos al usuario con ese correo electronico ( si lo encuentra lo guarda ):
        login_user = User.query.filter_by(email=request.json['email']).one()

        # Verificamos que el password sea correcto:
        password_from_db = login_user.password #  Si loguin_user está vacio, da error y se va al "Except".
        true_o_false = bcrypt.check_password_hash(password_from_db, password)
        
        # Si es verdadero generamos un token y lo devuelve en una respuesta JSON:
        if true_o_false:
            expires = timedelta(minutes=30)  # pueden ser "hours", "minutes", "days","seconds"

            user_id = login_user.id       # recuperamos el id del usuario para crear el token...
            access_token = create_access_token(identity=user_id, expires_delta=expires)   # creamos el token con tiempo vencimiento
            return jsonify({ 'access_token':access_token}), 200  # Enviamos el token al front ( si es necesario serializamos el "login_user" y tambien lo enviamos en el objeto json )

        else:
            return {"Error":"Contraseña  incorrecta"}
    
    except Exception as e:
        return {"Error":"El email proporcionado no corresponde a ninguno registrado: " + str(e)}, 500
    
# EJEMPLO DE RUTA RESTRINGIDA POR TOKEN. ( LA MISMA RECUPERA TODOS LOS USERS Y LO ENVIA PARA QUIEN ESTÉ LOGUEADO )
    
@admin_bp.route('/users')
@jwt_required()  # Decorador para requerir autenticación con JWT
def show_users():