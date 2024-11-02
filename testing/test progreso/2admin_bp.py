from flask import Blueprint, send_file, request, jsonify, render_template
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, jwt_required
from models import User
from database import db
from datetime import timedelta
from routes.utils import exportar_reporte_excel
import threading
import time

admin_bp = Blueprint('admin', __name__)
bcrypt = Bcrypt()
jwt = JWTManager()

# Variable global para el estado de la tarea
task_status = {'state': 'PENDING', 'progress': 0}

def long_task(username, password):
    global task_status
    task_status['state'] = 'IN_PROGRESS'
    task_status['progress'] = 0

    # Simula el proceso de exportación de reportes
    for i in range(1, 11):
        time.sleep(1)  # Simula un paso del proceso
        task_status['progress'] = i * 10

    excel_file = exportar_reporte_excel(username, password)
    if excel_file:
        task_status['state'] = 'COMPLETED'
        task_status['file'] = excel_file
    else:
        task_status['state'] = 'FAILED'

@admin_bp.route('/usuarios_por_asignacion_para_gestores', methods=['POST'])
def exportar_reporte():
    data = request.get_json()
    if 'username' not in data or 'password' not in data:
        return jsonify({"error": "Falta username o password en el cuerpo JSON"}), 400
    username = data['username']
    password = data['password']

    # Inicia la tarea en un hilo separado
    thread = threading.Thread(target=long_task, args=(username, password))
    thread.start()

    return jsonify({'message': 'Task started'}), 202

@admin_bp.route('/task-status', methods=['GET'])
def task_status_route():
    global task_status
    return jsonify(task_status)

@admin_bp.route('/get-file', methods=['GET'])
def get_file():
    global task_status
    if task_status.get('state') == 'COMPLETED' and 'file' in task_status:
        return send_file(task_status['file'], as_attachment=True, download_name='reporte_excel.xlsx')
    else:
        return "No file available", 404

@admin_bp.route('/', methods=['GET'])
def show_hello_world():
    return render_template('instructions.html')
