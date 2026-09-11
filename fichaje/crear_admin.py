"""Utilidad explícita para crear el primer administrador."""

from getpass import getpass

from script_guards import require_production_script


def crear_administrador_con_datos(
    session,
    modelo_usuario,
    generar_hash,
    *,
    nombre,
    email,
    password,
):
    """Valida y persiste un administrador sin depender de la interfaz interactiva."""
    from app.services.autenticacion import (
        normalizar_email,
        normalizar_nombre,
        validar_password,
    )
    from app.services.usuarios import (
        USUARIO_EMAIL_DUPLICADO,
        buscar_usuario_por_email,
        persistir_usuario,
    )

    nombre = normalizar_nombre(nombre)
    email = normalizar_email(email)
    password = validar_password(password, password)

    if buscar_usuario_por_email(session, modelo_usuario, email) is not None:
        session.rollback()
        from app.services.usuarios import ResultadoAltaUsuario

        return ResultadoAltaUsuario(USUARIO_EMAIL_DUPLICADO)

    return persistir_usuario(
        session,
        modelo_usuario,
        nombre=nombre,
        email=email,
        password_hash=generar_hash(password),
        puesto="Administración",
        admin=True,
    )


def main():
    require_production_script(
        "FICHAJE_ALLOW_CREATE_ADMIN",
        "Admin creation",
    )

    from werkzeug.security import generate_password_hash

    from app import app, db
    from app.models import Usuario
    from app.services.autenticacion import (
        ErrorValidacionAutenticacion,
        normalizar_email,
        normalizar_nombre,
        validar_password,
    )

    try:
        nombre = normalizar_nombre(input("Nombre del administrador: "))
        email = normalizar_email(input("Email del administrador: "))
        password = validar_password(
            getpass("Contraseña: "),
            getpass("Confirma la contraseña: "),
        )
    except ErrorValidacionAutenticacion as exc:
        print(f"Datos no válidos: {exc}")
        return 1

    with app.app_context():
        resultado = crear_administrador_con_datos(
            db.session,
            Usuario,
            generate_password_hash,
            nombre=nombre,
            email=email,
            password=password,
        )
        from app.services.usuarios import (
            USUARIO_CREADO,
            USUARIO_EMAIL_DUPLICADO,
        )

        if resultado.codigo == USUARIO_EMAIL_DUPLICADO:
            print("Ya existe un usuario con ese email.")
            return 1
        if resultado.codigo != USUARIO_CREADO:
            print("No se pudo crear el administrador.")
            return 1

    print("Administrador creado correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
