import os # para saber la ruta absoluta de la db si no la encontramos
from flask_bcrypt import Bcrypt  # para encriptar y comparar
from flask import Flask, request, jsonify # Para endpoints
from flask_sqlalchemy import SQLAlchemy  # Para rutas
from flask_jwt_extended import  JWTManager, create_access_token, jwt_required, get_jwt_identity
from admin_bp import admin_bp                       # Acá importamos rutas admin
from public_bp import public_bp                     # Acá importamos rutas public
from database import db                             # Acá importamos la base de datos inicializada
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# ENCRIPTACION JWT y BCRYPT-------

app.config["JWT_SECRET_KEY"] = "valor-variable"  # clave secreta para firmar los tokens.( y a futuro va en un archivo .env)
jwt = JWTManager(app)  # isntanciamos jwt de JWTManager utilizando app para tener las herramientas de encriptacion.
bcrypt = Bcrypt(app)   # para encriptar password


# REGISTRAR BLUEPRINTS ( POSIBILIDAD DE UTILIZAR EL ENTORNO DE LA app EN OTROS ARCHIVOS Y GENERAR RUTAS EN LOS MISMOS )


app.register_blueprint(admin_bp, url_prefix='/admin')  # poder registrarlo como un blueprint ( parte del app )
                                                       # y si queremos podemos darle toda un path base como en el ejemplo '/admin'

app.register_blueprint(public_bp, url_prefix='/public')  # blueprint public_bp



# DATABASE---------------
db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance', 'mydatabase.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'


print(f"Ruta de la base de datos: {db_path}")


if not os.path.exists(os.path.dirname(db_path)): # Nos aseguramos que se cree carpeta instance automatico para poder tener mydatabase.db dentro.
    os.makedirs(os.path.dirname(db_path))

with app.app_context():
    db.init_app(app)
    db.create_all() # Nos aseguramos que este corriendo en el contexto del proyecto.
# -----------------------

# AL FINAL ( detecta que encendimos el servidor desde terminal y nos da detalles de los errores )
if __name__ == '__main__':
    app.run(debug=True)