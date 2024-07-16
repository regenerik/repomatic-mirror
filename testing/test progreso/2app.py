import os
from flask_bcrypt import Bcrypt
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from admin_bp import admin_bp
from public_bp import public_bp
from database import db
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

app.config["JWT_SECRET_KEY"] = "valor-variable"
jwt = JWTManager(app)
bcrypt = Bcrypt(app)

app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(public_bp, url_prefix='/public')

db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance', 'mydatabase.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

print(f"Ruta de la base de datos: {db_path}")

if not os.path.exists(os.path.dirname(db_path)):
    os.makedirs(os.path.dirname(db_path))

with app.app_context():
    db.init_app(app)
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
