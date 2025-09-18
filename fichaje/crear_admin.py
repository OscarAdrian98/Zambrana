from app import app, db
from app.models import Usuario
from werkzeug.security import generate_password_hash

with app.app_context():
    nombre = "Administrador"
    email = ""
    contraseña_plana = ""  # Puedes cambiarla luego
    password_hash = generate_password_hash(contraseña_plana)

    # Verifica si ya existe
    existente = Usuario.query.filter_by(email=email).first()
    if existente:
        print("⚠️ El usuario ya existe.")
    else:
        nuevo_admin = Usuario(
            nombre=nombre,
            email=email,
            password_hash=password_hash,
            admin=True
        )
        db.session.add(nuevo_admin)
        db.session.commit()
        print("✅ Usuario administrador creado con éxito.")