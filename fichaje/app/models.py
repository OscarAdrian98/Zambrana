from app import db
from flask_login import UserMixin
from datetime import datetime

class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    admin = db.Column(db.Boolean, default=False)
    puesto = db.Column(db.String(100))

class Fichaje(db.Model):
    __tablename__ = 'fichajes'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    fecha = db.Column(db.Date, nullable=False)

    # Nuevos campos para trazabilidad legal
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    creado_por_admin = db.Column(db.Boolean, default=False)
    eliminado = db.Column(db.Boolean, default=False)

    usuario = db.relationship('Usuario', backref='fichajes')

class Modificacion(db.Model):
    __tablename__ = 'modificaciones'

    id = db.Column(db.Integer, primary_key=True)
    fichaje_id = db.Column(db.Integer, db.ForeignKey('fichajes.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow)
    campo_modificado = db.Column(db.String(50), nullable=False)
    valor_anterior = db.Column(db.String(20))
    valor_nuevo = db.Column(db.String(20))

    fichaje = db.relationship('Fichaje', backref='modificaciones', lazy=True)
    admin = db.relationship('Usuario', backref='modificaciones_hechas', lazy=True)

class RegistroHorario(db.Model):
    __tablename__ = 'registro_horario'

    id = db.Column(db.Integer, primary_key=True)
    fichaje_id = db.Column(db.Integer, db.ForeignKey('fichajes.id'), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # 'entrada' o 'salida'
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    creado_por_admin = db.Column(db.Boolean, default=False)
    eliminado = db.Column(db.Boolean, default=False)
    origen = db.Column(db.String(20), default='Tienda')

    fichaje = db.relationship('Fichaje', backref=db.backref('registros', lazy='joined', order_by="RegistroHorario.timestamp"))

class Ausencia(db.Model):
    __tablename__ = 'ausencias'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    tipo = db.Column(db.String(50), nullable=False)  # 'vacaciones', 'enfermedad', etc.
    observaciones = db.Column(db.String(255))
    creado_por_admin = db.Column(db.Boolean, default=False)

    usuario = db.relationship('Usuario', backref='ausencias')

class SabadoAsignado(db.Model):
    __tablename__ = 'sabados_asignados'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    fecha = db.Column(db.Date, nullable=False)

    usuario = db.relationship('Usuario', backref='sabados_asignados')