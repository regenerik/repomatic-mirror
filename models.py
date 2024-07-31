from database import db
from datetime import datetime


class User(db.Model):
    dni = db.Column(db.Integer, primary_key=True)
    id = db.Column(db.Integer)
    name = db.Column(db.String(50))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(255))
    admin = db.Column(db.Boolean)

class Permitido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dni = db.Column(db.Integer, db.ForeignKey('user.id'))


class Reporte(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    report_url = db.Column(db.String(255), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    size = db.Column(db.Float, nullable=False)
    elapsed_time = db.Column(db.String(50), nullable=True)
    title = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow) # revisar si .UTC va o si cambiamos a .utcnow

