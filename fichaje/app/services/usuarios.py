"""Alta transaccional y clasificación segura de duplicados de usuario."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError


USUARIO_CREADO = "usuario_creado"
USUARIO_EMAIL_DUPLICADO = "usuario_email_duplicado"
USUARIO_ERROR_INTEGRIDAD = "usuario_error_integridad"
USUARIO_ERROR_PERSISTENCIA = "usuario_error_persistencia"
RESTRICCION_EMAIL_USUARIO = "uq_usuarios_email"


@dataclass(frozen=True)
class ResultadoAltaUsuario:
    codigo: str
    usuario: object | None = None
    codigo_motor: int | None = None


def buscar_usuario_por_email(session, modelo_usuario, email):
    """Precomprobación amigable; la restricción física sigue siendo la autoridad."""
    return session.execute(
        select(modelo_usuario)
        .where(func.lower(modelo_usuario.email) == email)
        .order_by(modelo_usuario.id)
        .limit(1)
    ).scalar_one_or_none()


def es_duplicado_email_usuario(error):
    """Reconoce sólo la violación física de ``usuarios.email``."""
    if not isinstance(error, IntegrityError):
        return False

    original = error.orig
    argumentos = getattr(original, "args", ())
    codigo = argumentos[0] if argumentos else None
    mensaje = " ".join(str(valor) for valor in argumentos).casefold()

    if codigo == 1062:
        return RESTRICCION_EMAIL_USUARIO.casefold() in mensaje

    return "unique constraint failed" in mensaje and "usuarios.email" in mensaje


def persistir_usuario(
    session,
    modelo_usuario,
    *,
    nombre,
    email,
    password_hash,
    puesto,
    admin,
):
    """Inserta y confirma una vez; siempre deja la sesión reutilizable al fallar."""
    usuario = modelo_usuario(
        nombre=nombre,
        email=email,
        password_hash=password_hash,
        puesto=puesto,
        admin=admin,
    )
    try:
        session.add(usuario)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        argumentos = getattr(error.orig, "args", ())
        codigo_motor = argumentos[0] if argumentos else None
        if not isinstance(codigo_motor, int):
            codigo_motor = None
        codigo = (
            USUARIO_EMAIL_DUPLICADO
            if es_duplicado_email_usuario(error)
            else USUARIO_ERROR_INTEGRIDAD
        )
        return ResultadoAltaUsuario(codigo, codigo_motor=codigo_motor)
    except Exception as error:
        session.rollback()
        original = getattr(error, "orig", error)
        argumentos = getattr(original, "args", ())
        codigo_motor = argumentos[0] if argumentos else None
        if not isinstance(codigo_motor, int):
            codigo_motor = None
        if codigo_motor == 1020:
            try:
                existente = buscar_usuario_por_email(
                    session,
                    modelo_usuario,
                    email,
                )
            except Exception:
                session.rollback()
            else:
                if existente is not None:
                    return ResultadoAltaUsuario(
                        USUARIO_EMAIL_DUPLICADO,
                        codigo_motor=codigo_motor,
                    )
        return ResultadoAltaUsuario(
            USUARIO_ERROR_PERSISTENCIA,
            codigo_motor=codigo_motor,
        )

    return ResultadoAltaUsuario(USUARIO_CREADO, usuario)
