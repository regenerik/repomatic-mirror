import os # para saber la ruta absoluta de la db si no la encontramos
from flask_bcrypt import Bcrypt  # para encriptar y comparar
from flask import Flask, request, jsonify # Para endpoints
from flask_sqlalchemy import SQLAlchemy  # Para rutas
from flask_jwt_extended import  JWTManager, create_access_token, jwt_required, get_jwt_identity
from routes.admin_bp import admin_bp                       # Acá importamos rutas admin
from public_bp import public_bp                     # Acá importamos rutas public
from routes.quinto_survey_bp import quinto_survey_bp
from routes.cuarto_survey_bp import cuarto_survey_bp
from routes.form_gestores_bp import form_gestores_bp
from routes.chat_moes_bp import chat_moes_bp
from routes.rescate_actividades_bp import rescate_actividades_bp
from routes.clasifica_topicos_mensual_bp import clasifica_topicos_mensual_bp
from routes.rescate_reportes_bp import rescate_reportes_bp
from routes.encuestas_cursos_bp import encuestas_cursos_bp
from routes.segundo_survey_bp import segundo_survey_bp
from routes.tercer_survey_bp import tercer_survey_bp
from routes.resumen_comentarios_apies_bp import resumen_comentarios_apies_bp
from routes.diarios_clasifica_sentimientos_bp import diarios_clasifica_sentimientos_bp
from routes.clasifica_comentarios_individuales_bp import clasifica_comentarios_individuales_bp
from database import db                             # Acá importamos la base de datos inicializada
from flask_cors import CORS                         # Permisos de consumo
from extensions import init_extensions              # Necesario para que funcione el executor en varios archivos en simultaneo
from models import TodosLosReportes, User  # Importamos el modelo para TodosLosReportes
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

# Inicializa los extensiones
init_extensions(app)

CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# ENCRIPTACION JWT y BCRYPT-------

app.config["JWT_SECRET_KEY"] = "valor-variable"  # clave secreta para firmar los tokens.( y a futuro va en un archivo .env)
jwt = JWTManager(app)  # isntanciamos jwt de JWTManager utilizando app para tener las herramientas de encriptacion.
bcrypt = Bcrypt(app)   # para encriptar password


# REGISTRAR BLUEPRINTS ( POSIBILIDAD DE UTILIZAR EL ENTORNO DE LA app EN OTROS ARCHIVOS Y GENERAR RUTAS EN LOS MISMOS )


app.register_blueprint(admin_bp)  # poder registrarlo como un blueprint ( parte del app )
                                                       # y si queremos podemos darle toda un path base como en el ejemplo '/admin'

app.register_blueprint(public_bp, url_prefix='/public')  # blueprint public_bp

app.register_blueprint(rescate_reportes_bp, url_prefix='/') 

app.register_blueprint(encuestas_cursos_bp, url_prefix='/') 

app.register_blueprint(resumen_comentarios_apies_bp, url_prefix='/') 

app.register_blueprint(clasifica_comentarios_individuales_bp, url_prefix='/')

app.register_blueprint(diarios_clasifica_sentimientos_bp, url_prefix='/')

app.register_blueprint(clasifica_topicos_mensual_bp, url_prefix='/')

app.register_blueprint(segundo_survey_bp, url_prefix='/')

app.register_blueprint(tercer_survey_bp, url_prefix='/')

app.register_blueprint(rescate_actividades_bp, url_prefix='/')

app.register_blueprint(chat_moes_bp, url_prefix='/')

app.register_blueprint(form_gestores_bp, url_prefix='/')

app.register_blueprint(cuarto_survey_bp, url_prefix='/')

app.register_blueprint(quinto_survey_bp, url_prefix='/')

# DATABASE---------------
db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance', 'mydatabase.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'


print(f"Ruta de la base de datos: {db_path}")


if not os.path.exists(os.path.dirname(db_path)): # Nos aseguramos que se cree carpeta instance automatico para poder tener mydatabase.db dentro.
    os.makedirs(os.path.dirname(db_path))

from logging_config import logger
# Función para recargar los reportes (siempre borra lo anterior y carga lo nuevo)
def cargar_todos_los_reportes_iniciales():
    logger.info("Recargando reportes en tabla...")
    # Lista de reportes que queremos cargar
    reportes_nuevos = [
        {"report_url": "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=133", "title": "USUARIOS POR ASIGNACION PARA GESTORES"},
        {"report_url": "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=302&sid=712", "title": "Clon de CURSADA RETAIL"},
        {"report_url": "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=248", "title": "Cursos con detalle"},
        {"report_url": "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=130", "title": "VERIFICA USUARIOS PARA GESTORES"},
        {"report_url": "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=204", "title": "T2_CURSOS_HV"},
        {"report_url": "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=205", "title": "T2_APIES_HV"},
        {"report_url": "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=261", "title": "T2_FACILITADOR_SEMINAR"},
        {"report_url": "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=296&sid=713", "title": "CURSADA NO RETAIL"},
        {"report_url": "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=306", "title": "Inscripciones Marketplace"},
        {"report_url": "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=210&sid=731", "title": "AVANCE DE PROGRAMAS"},
        {"report_url": "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=210&sid=732" ,"title": "AVANCE DE PROGRAMAS"},
        {"report_url": "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=210&sid=734" ,"title": "AVANCE DE PROGRAMAS"},
        {"report_url": "https://www.campuscomercialypf.com/mod/perform/reporting/performance/activity.php?activity_id=9&all_activities=true" ,"title":"Todas las actividades - 237099 registro/s"},
        {"report_url": "https://www.campuscomercialypf.com/totara/reportbuilder/report.php?id=249" ,"title": "+YPF 2025 Avance por usuarios"}
    ]

    # Borramos todos los reportes actuales
    TodosLosReportes.query.delete()
    db.session.commit()  # Confirmamos el borrado en la base de datos

    # Verificamos si la tabla quedó vacía
    reportes_actuales = TodosLosReportes.query.all()
    if reportes_actuales:
        print("Error: No se pudieron eliminar los reportes anteriores.")
        return  # Salimos de la función si no se eliminaron correctamente

    print("Los reportes anteriores fueron eliminados correctamente.")

    # Cargamos los nuevos reportes
    nuevos_registros = [
        TodosLosReportes(report_url=reporte["report_url"], title=reporte["title"])
        for reporte in reportes_nuevos
    ]
    db.session.bulk_save_objects(nuevos_registros)
    db.session.commit()
    logger.info(f"Los reportes fueron actualizados. Se cargaron {len(nuevos_registros)} reportes nuevos.")





# Función para cargar los usuarios iniciales
def cargar_usuarios_iniciales():
    # if User.query.count() == 0:  # Verificamos si la tabla User está vacía
    usuarios_iniciales = [
        {
            "email": os.getenv('EMAIL1'),
            "name": os.getenv('NAME1'),
            "password": os.getenv('PASSWORD1'),
            "dni": os.getenv('DNI1'),
            "admin": os.getenv('ADMIN1') == 'True',
            "url_image": os.getenv('URL_IMAGE1')
        },
        {
            "email": os.getenv('EMAIL2'),
            "name": os.getenv('NAME2'),
            "password": os.getenv('PASSWORD2'),
            "dni": os.getenv('DNI2'),
            "admin": os.getenv('ADMIN2') == 'True',
            "url_image": os.getenv('URL_IMAGE2')
        },
        {
            "email": os.getenv('EMAIL3'),
            "name": os.getenv('NAME3'),
            "password": os.getenv('PASSWORD3'),
            "dni": os.getenv('DNI3'),
            "admin": os.getenv('ADMIN3') == 'True',
            "url_image": os.getenv('URL_IMAGE3')
        },
        {
            "email": os.getenv('EMAIL4'),
            "name": os.getenv('NAME4'),
            "password": os.getenv('PASSWORD4'),
            "dni": os.getenv('DNI4'),
            "admin": os.getenv('ADMIN4') == 'True',
            "url_image": os.getenv('URL_IMAGE4')
        },
        {
            "email": os.getenv('EMAIL5'),
            "name": os.getenv('NAME5'),
            "password": os.getenv('PASSWORD5'),
            "dni": os.getenv('DNI5'),
            "admin": os.getenv('ADMIN5') == 'True',
            "url_image": os.getenv('URL_IMAGE5')
        },
        {
            "email": os.getenv('EMAIL6'),
            "name": os.getenv('NAME6'),
            "password": os.getenv('PASSWORD6'),
            "dni": os.getenv('DNI6'),
            "admin": os.getenv('ADMIN6') == 'True',
            "url_image": os.getenv('URL_IMAGE6')
        },
        {
            "email": os.getenv('EMAIL7'),
            "name": os.getenv('NAME7'),
            "password": os.getenv('PASSWORD7'),
            "dni": os.getenv('DNI7'),
            "admin": os.getenv('ADMIN7') == 'True',
            "url_image": os.getenv('URL_IMAGE7')
        },
        {
            "email": os.getenv('EMAIL8'),
            "name": os.getenv('NAME8'),
            "password": os.getenv('PASSWORD8'),
            "dni": os.getenv('DNI8'),
            "admin": os.getenv('ADMIN8') == 'True',
            "url_image": os.getenv('URL_IMAGE8')
        },
        {
            "email": os.getenv('EMAIL9'),
            "name": os.getenv('NAME9'),
            "password": os.getenv('PASSWORD9'),
            "dni": os.getenv('DNI9'),
            "admin": os.getenv('ADMIN9') == 'True',
            "url_image": os.getenv('URL_IMAGE9')
        },
        {
            "email": os.getenv('EMAIL10'),
            "name": os.getenv('NAME10'),
            "password": os.getenv('PASSWORD10'),
            "dni": os.getenv('DNI10'),
            "admin": os.getenv('ADMIN10') == 'True',
            "url_image": os.getenv('URL_IMAGE10')
        },
        {
            "email": os.getenv('EMAIL11'),
            "name": os.getenv('NAME11'),
            "password": os.getenv('PASSWORD11'),
            "dni": os.getenv('DNI11'),
            "admin": os.getenv('ADMIN11') == 'True',
            "url_image": os.getenv('URL_IMAGE11')
        },
        {
            "email": os.getenv('EMAIL12'),
            "name": os.getenv('NAME12'),
            "password": os.getenv('PASSWORD12'),
            "dni": os.getenv('DNI12'),
            "admin": os.getenv('ADMIN12') == 'True',
            "url_image": os.getenv('URL_IMAGE12')
        }
    ]

    for usuario in usuarios_iniciales:
        password_hash = bcrypt.generate_password_hash(usuario['password']).decode('utf-8')
        new_user = User(
            email=usuario['email'],
            name=usuario['name'],
            password=password_hash,
            dni=usuario['dni'],
            admin=usuario['admin'],
            url_image=usuario['url_image']
        )
        db.session.add(new_user)

    db.session.commit()
    print("Usuarios iniciales cargados correctamente.")

with app.app_context():
    db.init_app(app)
    db.create_all() # Nos aseguramos que este corriendo en el contexto del proyecto.
    cargar_todos_los_reportes_iniciales()  # Cargamos los reportes iniciales
    cargar_usuarios_iniciales()
# -----------------------

# AL FINAL ( detecta que encendimos el servidor desde terminal y nos da detalles de los errores )
if __name__ == '__main__':
    app.run()

# EJECUTO CON : myenv\Scripts\activate
# waitress-serve --port=5000 app:app
