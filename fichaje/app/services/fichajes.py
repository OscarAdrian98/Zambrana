"""Registro transaccional de entradas y salidas realizadas por el usuario."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import logging
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import lazyload, noload

from app.models import Ausencia, Fichaje, Modificacion, RegistroHorario, Usuario
from app.services.ausencias import ahora_madrid, existe_ausencia_bloqueante
from app.services.edicion_fichajes import (
    ErrorEdicionFichaje,
    ErrorRegistroEdicionFichaje,
    ErrorSnapshotBorradoFichaje,
    ErrorSnapshotEdicionFichaje,
    combinar_fecha_hora,
    parsear_y_validar_formulario,
    preparar_edicion,
    texto_tramo,
    validar_snapshot_borrado_firmado,
    validar_snapshot_firmado,
)
from app.services.horarios import reconstruir_tramos


OK_ENTRADA = "OK_ENTRADA"
OK_SALIDA = "OK_SALIDA"
TIPO_INVALIDO = "TIPO_INVALIDO"
ORIGEN_INVALIDO = "ORIGEN_INVALIDO"
AUSENCIA_BLOQUEANTE = "AUSENCIA_BLOQUEANTE"
SALIDA_SIN_ENTRADA = "SALIDA_SIN_ENTRADA"
ENTRADA_DUPLICADA = "ENTRADA_DUPLICADA"
SALIDA_DUPLICADA = "SALIDA_DUPLICADA"
FICHAJES_ACTIVOS_MULTIPLES = "FICHAJES_ACTIVOS_MULTIPLES"
SECUENCIA_ANOMALA = "SECUENCIA_ANOMALA"
USUARIO_NO_ENCONTRADO = "USUARIO_NO_ENCONTRADO"
ERROR_PERSISTENCIA = "ERROR_PERSISTENCIA"

LECTURA_FICHAJE_ACTIVO_NINGUNO = "ninguno"
LECTURA_FICHAJE_ACTIVO_UNICO = "unico"
LECTURA_FICHAJE_ACTIVO_MULTIPLE = "multiple"

AUTO_SALIDA_CREADA = "AUTO_SALIDA_CREADA"
AUTO_YA_CERRADO = "AUTO_YA_CERRADO"
AUTO_SIN_FICHAJE_ACTIVO = "AUTO_SIN_FICHAJE_ACTIVO"
AUTO_SIN_TRAMO_ABIERTO = "AUTO_SIN_TRAMO_ABIERTO"
AUTO_AUSENCIA_BLOQUEANTE = "AUTO_AUSENCIA_BLOQUEANTE"
AUTO_SECUENCIA_ANOMALA = "AUTO_SECUENCIA_ANOMALA"
AUTO_FICHAJES_ACTIVOS_MULTIPLES = "AUTO_FICHAJES_ACTIVOS_MULTIPLES"
AUTO_TIMESTAMP_INVALIDO = "AUTO_TIMESTAMP_INVALIDO"
AUTO_USUARIO_INEXISTENTE = "AUTO_USUARIO_INEXISTENTE"
AUTO_ERROR_PERSISTENCIA = "AUTO_ERROR_PERSISTENCIA"

ADMIN_FICHAJE_CREADO = "ADMIN_FICHAJE_CREADO"
ADMIN_USUARIO_INEXISTENTE = "ADMIN_USUARIO_INEXISTENTE"
ADMIN_ADMINISTRADOR_INEXISTENTE = "ADMIN_ADMINISTRADOR_INEXISTENTE"
ADMIN_SIN_PERMISOS = "ADMIN_SIN_PERMISOS"
ADMIN_FECHA_INVALIDA = "ADMIN_FECHA_INVALIDA"
ADMIN_HORAS_INVALIDAS = "ADMIN_HORAS_INVALIDAS"
ADMIN_TRAMO_INVALIDO = "ADMIN_TRAMO_INVALIDO"
ADMIN_FICHAJE_YA_EXISTENTE = "ADMIN_FICHAJE_YA_EXISTENTE"
ADMIN_FICHAJES_ACTIVOS_MULTIPLES = "ADMIN_FICHAJES_ACTIVOS_MULTIPLES"
ADMIN_ERROR_PERSISTENCIA = "ADMIN_ERROR_PERSISTENCIA"

ADMIN_EDICION_ACTUALIZADA = "ADMIN_EDICION_ACTUALIZADA"
ADMIN_EDICION_SIN_CAMBIOS = "ADMIN_EDICION_SIN_CAMBIOS"
ADMIN_EDICION_ADMINISTRADOR_INEXISTENTE = (
    "ADMIN_EDICION_ADMINISTRADOR_INEXISTENTE"
)
ADMIN_EDICION_SIN_PERMISOS = "ADMIN_EDICION_SIN_PERMISOS"
ADMIN_EDICION_FICHAJE_INEXISTENTE = "ADMIN_EDICION_FICHAJE_INEXISTENTE"
ADMIN_EDICION_FICHAJE_ELIMINADO = "ADMIN_EDICION_FICHAJE_ELIMINADO"
ADMIN_EDICION_USUARIO_INEXISTENTE = "ADMIN_EDICION_USUARIO_INEXISTENTE"
ADMIN_EDICION_FICHAJES_ACTIVOS_MULTIPLES = (
    "ADMIN_EDICION_FICHAJES_ACTIVOS_MULTIPLES"
)
ADMIN_EDICION_TRAMOS_INVALIDOS = "ADMIN_EDICION_TRAMOS_INVALIDOS"
ADMIN_EDICION_REGISTRO_AJENO = "ADMIN_EDICION_REGISTRO_AJENO"
ADMIN_EDICION_CONFLICTO_CONCURRENTE = "ADMIN_EDICION_CONFLICTO_CONCURRENTE"
ADMIN_EDICION_ERROR_PERSISTENCIA = "ADMIN_EDICION_ERROR_PERSISTENCIA"

ADMIN_BORRADO_ELIMINADO = "ADMIN_BORRADO_ELIMINADO"
ADMIN_BORRADO_YA_ELIMINADO = "ADMIN_BORRADO_YA_ELIMINADO"
ADMIN_BORRADO_ADMINISTRADOR_INEXISTENTE = (
    "ADMIN_BORRADO_ADMINISTRADOR_INEXISTENTE"
)
ADMIN_BORRADO_SIN_PERMISOS = "ADMIN_BORRADO_SIN_PERMISOS"
ADMIN_BORRADO_FICHAJE_INEXISTENTE = "ADMIN_BORRADO_FICHAJE_INEXISTENTE"
ADMIN_BORRADO_USUARIO_INEXISTENTE = "ADMIN_BORRADO_USUARIO_INEXISTENTE"
ADMIN_BORRADO_CONFLICTO_CONCURRENTE = "ADMIN_BORRADO_CONFLICTO_CONCURRENTE"
ADMIN_BORRADO_ERROR_PERSISTENCIA = "ADMIN_BORRADO_ERROR_PERSISTENCIA"

ORIGENES_USUARIO = {"tienda": "Tienda", "remoto": "Remoto"}
ORIGENES_HISTORICOS = {**ORIGENES_USUARIO, "auto": "Auto"}


class ErrorRegistroFichaje(ValueError):
    def __init__(self, codigo: str, *, detalle: str | None = None):
        super().__init__(codigo)
        self.codigo = codigo
        self.detalle = detalle


@dataclass(frozen=True)
class EstadoSecuencia:
    siguiente_tipo: str
    entrada_abierta: object | None


@dataclass(frozen=True)
class ResultadoRegistroFichaje:
    codigo: str
    tipo: str
    origen: str
    instante: datetime
    fecha: date


@dataclass(frozen=True)
class ResultadoSalidaAutomatica:
    codigo: str
    instante: datetime | None
    fecha: date | None


@dataclass(frozen=True)
class ResultadoLecturaFichajeActivo:
    """Resultado no ambiguo de consultar la cabecera activa de un día.

    ``cantidad_detectada`` vale dos cuando se han encontrado dos o más
    cabeceras: la consulta se limita deliberadamente a lo necesario para
    detectar la incidencia y nunca devuelve una cabecera en ese caso.
    """

    estado: str
    fichaje: Fichaje | None
    cantidad_detectada: int


@dataclass(frozen=True)
class ResultadoCreacionFichajeAdministrativo:
    codigo: str
    fichaje_id: int | None
    usuario_id: int | None
    fecha: date | None


@dataclass(frozen=True)
class EntradaEdicionFichajeAdministrativo:
    snapshot: str
    campos: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ResultadoEdicionFichajeAdministrativo:
    codigo: str
    fichaje_id: int | None
    usuario_id: int | None
    fecha: date | None
    mensaje: str | None = None


@dataclass(frozen=True)
class ResultadoBorradoFichajeAdministrativo:
    codigo: str
    fichaje_id: int | None
    usuario_id: int | None
    fecha: date | None
    mensaje: str | None = None


_PATRON_FECHA_ADMIN = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_PATRON_HORA_ADMIN = re.compile(r"\A[0-9]{2}:[0-9]{2}\Z")


def normalizar_tipo(tipo) -> str:
    if not isinstance(tipo, str):
        raise ErrorRegistroFichaje(TIPO_INVALIDO)
    normalizado = tipo.strip().lower()
    if normalizado not in {"entrada", "salida"}:
        raise ErrorRegistroFichaje(TIPO_INVALIDO)
    return normalizado


def _texto_origen_seguro(origen) -> str:
    if not isinstance(origen, str):
        raise ErrorRegistroFichaje(ORIGEN_INVALIDO)
    if any(unicodedata.category(caracter).startswith("C") for caracter in origen):
        raise ErrorRegistroFichaje(ORIGEN_INVALIDO)
    normalizado = origen.strip()
    if not normalizado or len(normalizado) > 20:
        raise ErrorRegistroFichaje(ORIGEN_INVALIDO)
    if "<" in normalizado or ">" in normalizado:
        raise ErrorRegistroFichaje(ORIGEN_INVALIDO)
    return normalizado


def normalizar_origen_usuario(origen) -> str:
    normalizado = _texto_origen_seguro(origen)
    try:
        return ORIGENES_USUARIO[normalizado.casefold()]
    except KeyError as exc:
        raise ErrorRegistroFichaje(ORIGEN_INVALIDO) from exc


def _normalizar_origen_historico(origen) -> str:
    if origen is None or origen == "":
        return "Tienda"
    try:
        normalizado = _texto_origen_seguro(origen)
        return ORIGENES_HISTORICOS[normalizado.casefold()]
    except (KeyError, ErrorRegistroFichaje) as exc:
        raise ErrorRegistroFichaje(SECUENCIA_ANOMALA) from exc


def analizar_secuencia(
    registros,
    fecha_fichaje: date,
) -> EstadoSecuencia:
    """Valida una secuencia activa sin corregir ni omitir anomalías."""
    ordenados = list(registros)
    vistos = set()
    entrada_abierta = None
    hubo_registros = False

    for registro in ordenados:
        timestamp = getattr(registro, "timestamp", None)
        if not isinstance(timestamp, datetime):
            raise ErrorRegistroFichaje(SECUENCIA_ANOMALA)
        if timestamp.date() != fecha_fichaje or timestamp in vistos:
            raise ErrorRegistroFichaje(SECUENCIA_ANOMALA)
        vistos.add(timestamp)

        tipo = getattr(registro, "tipo", None)
        if tipo not in {"entrada", "salida"}:
            raise ErrorRegistroFichaje(SECUENCIA_ANOMALA)

        if tipo == "entrada":
            if entrada_abierta is not None:
                raise ErrorRegistroFichaje(ENTRADA_DUPLICADA)
            entrada_abierta = registro
        else:
            if entrada_abierta is None:
                codigo = SALIDA_DUPLICADA if hubo_registros else SALIDA_SIN_ENTRADA
                raise ErrorRegistroFichaje(codigo)
            if timestamp <= entrada_abierta.timestamp:
                raise ErrorRegistroFichaje(SECUENCIA_ANOMALA)
            entrada_abierta = None
        hubo_registros = True

    return EstadoSecuencia(
        siguiente_tipo="salida" if entrada_abierta is not None else "entrada",
        entrada_abierta=entrada_abierta,
    )


def _con_bloqueo_si_disponible(session, statement):
    dialecto = session.get_bind().dialect.name
    if dialecto in {"mysql", "mariadb"}:
        return statement.with_for_update()
    return statement


def _rollback(session) -> None:
    try:
        session.rollback()
    except Exception:
        logging.error("No se pudo completar el rollback del fichaje.")


def _codigo_error_base_datos(error):
    original = getattr(error, "orig", None)
    argumentos = getattr(original, "args", ())
    if argumentos and isinstance(argumentos[0], int):
        return argumentos[0]
    return None


def _instante_local_sin_zona(instante: datetime, zona) -> datetime:
    if instante.tzinfo is None:
        return instante
    return instante.astimezone(zona).replace(tzinfo=None)


def _instante_madrid_segundos(instante) -> datetime:
    return ahora_madrid(instante).replace(microsecond=0)


def _bloquear_usuario(session, usuario_id):
    statement = _con_bloqueo_si_disponible(
        session,
        select(Usuario).where(Usuario.id == usuario_id),
    )
    return session.execute(statement).scalar_one_or_none()


def _consultar_ausencias(session, usuario_id, fecha):
    return session.execute(
        select(Ausencia)
        .where(Ausencia.usuario_id == usuario_id, Ausencia.fecha == fecha)
        .order_by(Ausencia.id)
    ).scalars().all()


def _consultar_fichajes_activos(session, usuario_id, fecha):
    statement = (
        select(Fichaje)
        .options(noload(Fichaje.registros))
        .where(
            Fichaje.usuario_id == usuario_id,
            Fichaje.fecha == fecha,
            Fichaje.eliminado.is_(False),
        )
        .order_by(Fichaje.id)
    )
    return session.execute(statement).scalars().unique().all()


def resolver_fichaje_activo(session, *, usuario_id, fecha):
    """Resuelve 0/1/múltiples cabeceras activas sin escribir ni bloquear."""
    if not _identificador_positivo(usuario_id):
        raise ValueError("usuario_id inválido")
    if not isinstance(fecha, date) or isinstance(fecha, datetime):
        raise ValueError("fecha inválida")

    fichajes = (
        session.execute(
            select(Fichaje)
            .options(lazyload(Fichaje.registros))
            .where(
                Fichaje.usuario_id == usuario_id,
                Fichaje.fecha == fecha,
                Fichaje.eliminado.is_(False),
            )
            .order_by(Fichaje.id)
            .limit(2)
        )
        .scalars()
        .unique()
        .all()
    )

    if not fichajes:
        return ResultadoLecturaFichajeActivo(
            estado=LECTURA_FICHAJE_ACTIVO_NINGUNO,
            fichaje=None,
            cantidad_detectada=0,
        )
    if len(fichajes) == 1:
        return ResultadoLecturaFichajeActivo(
            estado=LECTURA_FICHAJE_ACTIVO_UNICO,
            fichaje=fichajes[0],
            cantidad_detectada=1,
        )
    return ResultadoLecturaFichajeActivo(
        estado=LECTURA_FICHAJE_ACTIVO_MULTIPLE,
        fichaje=None,
        cantidad_detectada=2,
    )


def _parsear_fecha_administrativa(valor) -> date:
    if not isinstance(valor, str) or not _PATRON_FECHA_ADMIN.fullmatch(valor):
        raise ValueError("fecha administrativa inválida")
    return date.fromisoformat(valor)


def _parsear_hora_administrativa(valor) -> time:
    if not isinstance(valor, str) or not _PATRON_HORA_ADMIN.fullmatch(valor):
        raise ValueError("hora administrativa inválida")
    hora, minuto = (int(parte) for parte in valor.split(":"))
    return time(hour=hora, minute=minuto)


def _identificador_positivo(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


def crear_fichaje_administrativo(
    session,
    *,
    administrador_id,
    usuario_id,
    fecha,
    hora_entrada,
    hora_salida,
) -> ResultadoCreacionFichajeAdministrativo:
    """Crea una jornada administrativa completa en una sola transacción.

    La sesión recibida debe estar limpia. La operación es propietaria de la
    transacción y termina siempre mediante un único ``commit`` o ``rollback``.
    Los valores de trazabilidad se fuerzan en el dominio y no son configurables
    por el formulario ni por otros llamadores.
    """

    def omitir(codigo, *, fichaje_id=None, fecha_resultado=None):
        _rollback(session)
        return ResultadoCreacionFichajeAdministrativo(
            codigo=codigo,
            fichaje_id=fichaje_id,
            usuario_id=usuario_id if _identificador_positivo(usuario_id) else None,
            fecha=fecha_resultado,
        )

    if not _identificador_positivo(administrador_id):
        return omitir(ADMIN_ADMINISTRADOR_INEXISTENTE)
    if not _identificador_positivo(usuario_id):
        return omitir(ADMIN_USUARIO_INEXISTENTE)

    try:
        fecha_normalizada = _parsear_fecha_administrativa(fecha)
    except (TypeError, ValueError):
        return omitir(ADMIN_FECHA_INVALIDA)

    try:
        entrada_normalizada = _parsear_hora_administrativa(hora_entrada)
        salida_normalizada = _parsear_hora_administrativa(hora_salida)
    except (TypeError, ValueError):
        return omitir(
            ADMIN_HORAS_INVALIDAS,
            fecha_resultado=fecha_normalizada,
        )

    if entrada_normalizada >= salida_normalizada:
        return omitir(
            ADMIN_TRAMO_INVALIDO,
            fecha_resultado=fecha_normalizada,
        )

    try:
        usuario = _bloquear_usuario(session, usuario_id)
        if usuario is None:
            return omitir(
                ADMIN_USUARIO_INEXISTENTE,
                fecha_resultado=fecha_normalizada,
            )

        if administrador_id == usuario_id:
            administrador = usuario
        else:
            administrador = session.execute(
                select(Usuario).where(Usuario.id == administrador_id)
            ).scalar_one_or_none()
        if administrador is None:
            return omitir(
                ADMIN_ADMINISTRADOR_INEXISTENTE,
                fecha_resultado=fecha_normalizada,
            )
        if administrador.admin is not True:
            return omitir(
                ADMIN_SIN_PERMISOS,
                fecha_resultado=fecha_normalizada,
            )

        fichajes = _consultar_fichajes_activos(
            session,
            usuario_id,
            fecha_normalizada,
        )
        if len(fichajes) > 1:
            return omitir(
                ADMIN_FICHAJES_ACTIVOS_MULTIPLES,
                fecha_resultado=fecha_normalizada,
            )
        if fichajes:
            return omitir(
                ADMIN_FICHAJE_YA_EXISTENTE,
                fichaje_id=fichajes[0].id,
                fecha_resultado=fecha_normalizada,
            )

        fichaje = Fichaje(
            usuario_id=usuario_id,
            fecha=fecha_normalizada,
            fecha_creacion=ahora_madrid().replace(tzinfo=None, microsecond=0),
            creado_por_admin=True,
            eliminado=False,
        )
        session.add(fichaje)
        session.flush()
        fichaje_id = fichaje.id

        session.add_all(
            [
                RegistroHorario(
                    fichaje_id=fichaje_id,
                    tipo="entrada",
                    timestamp=datetime.combine(
                        fecha_normalizada,
                        entrada_normalizada,
                    ),
                    creado_por_admin=True,
                    eliminado=False,
                    origen="Tienda",
                ),
                RegistroHorario(
                    fichaje_id=fichaje_id,
                    tipo="salida",
                    timestamp=datetime.combine(
                        fecha_normalizada,
                        salida_normalizada,
                    ),
                    creado_por_admin=True,
                    eliminado=False,
                    origen="Tienda",
                ),
            ]
        )
        session.commit()
        return ResultadoCreacionFichajeAdministrativo(
            codigo=ADMIN_FICHAJE_CREADO,
            fichaje_id=fichaje_id,
            usuario_id=usuario_id,
            fecha=fecha_normalizada,
        )
    except Exception as exc:
        _rollback(session)
        logging.error(
            "Error técnico al crear fichaje administrativo (%s).",
            type(exc).__name__,
        )
        return ResultadoCreacionFichajeAdministrativo(
            codigo=ADMIN_ERROR_PERSISTENCIA,
            fichaje_id=None,
            usuario_id=usuario_id,
            fecha=fecha_normalizada,
        )


def _consultar_registros_activos(session, fichaje_id, *, bloquear=False):
    statement = (
        select(RegistroHorario)
        .where(
            RegistroHorario.fichaje_id == fichaje_id,
            RegistroHorario.eliminado == False,
        )
        .order_by(RegistroHorario.timestamp, RegistroHorario.id)
    )
    if bloquear:
        statement = _con_bloqueo_si_disponible(session, statement)
        statement = statement.execution_options(populate_existing=True)
    return session.execute(statement).scalars().all()


def _consultar_fichaje_bajo_bloqueo(session, fichaje_id):
    statement = select(
        Fichaje.id,
        Fichaje.usuario_id,
        Fichaje.fecha,
        Fichaje.eliminado,
    ).where(Fichaje.id == fichaje_id)
    statement = _con_bloqueo_si_disponible(session, statement)
    return session.execute(statement).one_or_none()


def _consultar_modelo_fichaje_bajo_bloqueo(session, fichaje_id):
    statement = (
        select(Fichaje)
        .options(lazyload(Fichaje.registros))
        .where(Fichaje.id == fichaje_id)
        .execution_options(populate_existing=True)
    )
    statement = _con_bloqueo_si_disponible(session, statement)
    return session.execute(statement).scalar_one_or_none()


def _consultar_ids_fichajes_activos_bajo_bloqueo(
    session,
    usuario_id,
    fecha,
):
    statement = (
        select(Fichaje.id)
        .where(
            Fichaje.usuario_id == usuario_id,
            Fichaje.fecha == fecha,
            Fichaje.eliminado.is_(False),
        )
        .order_by(Fichaje.id)
    )
    statement = _con_bloqueo_si_disponible(session, statement)
    return list(session.execute(statement).scalars())


def _origen_registro_administrativo(registro):
    return registro.origen or "Tienda"


def _crear_registro_editado(
    session,
    fichaje,
    tipo,
    hora,
    origen,
):
    registro = RegistroHorario(
        fichaje_id=fichaje.id,
        tipo=tipo,
        timestamp=combinar_fecha_hora(fichaje.fecha, hora),
        creado_por_admin=True,
        eliminado=False,
        origen=origen,
    )
    session.add(registro)
    return registro


def _crear_auditoria_edicion(
    session,
    fichaje,
    administrador_id,
    campo,
    anterior,
    nuevo,
    fecha_modificacion,
):
    campo = str(campo)
    anterior = str(anterior)
    nuevo = str(nuevo)
    if len(campo) > 50 or len(anterior) > 20 or len(nuevo) > 20:
        raise RuntimeError("La auditoría compacta supera la longitud permitida.")
    session.add(
        Modificacion(
            fichaje_id=fichaje.id,
            admin_id=administrador_id,
            campo_modificado=campo,
            valor_anterior=anterior,
            valor_nuevo=nuevo,
            fecha_modificacion=fecha_modificacion,
        )
    )


def _aplicar_edicion_fichaje(
    session,
    fichaje,
    registros_activos,
    solicitud,
    administrador_id,
    fecha_modificacion,
):
    registros = {registro.id: registro for registro in registros_activos}
    cambios = 0

    for tramo in solicitud.tramos:
        entrada_original = registros.get(tramo.entrada_id)
        salida_original = registros.get(tramo.salida_id)
        anterior = (
            texto_tramo(
                entrada_original.timestamp.time(),
                salida_original.timestamp.time() if salida_original else None,
            )
            if entrada_original
            else "-"
        )
        nuevo = texto_tramo(tramo.entrada, tramo.salida)

        if tramo.eliminar:
            if entrada_original is None and salida_original is None:
                continue
            for registro in (entrada_original, salida_original):
                if registro is not None:
                    registro.eliminado = True
                    cambios += 1
            _crear_auditoria_edicion(
                session,
                fichaje,
                administrador_id,
                "tramo_del",
                anterior,
                "DEL",
                fecha_modificacion,
            )
            continue

        presencia_salida_igual = (salida_original is None) == (tramo.salida is None)
        horas_iguales = (
            entrada_original is not None
            and entrada_original.timestamp.strftime("%H:%M")
            == tramo.entrada.strftime("%H:%M")
            and presencia_salida_igual
            and (
                salida_original is None
                or salida_original.timestamp.strftime("%H:%M")
                == tramo.salida.strftime("%H:%M")
            )
        )
        origen_entrada_igual = (
            entrada_original is not None
            and _origen_registro_administrativo(entrada_original) == tramo.origen
        )

        if horas_iguales and origen_entrada_igual:
            continue

        if entrada_original is None:
            _crear_registro_editado(
                session,
                fichaje,
                "entrada",
                tramo.entrada,
                tramo.origen,
            )
            cambios += 1
        elif (
            entrada_original.timestamp.strftime("%H:%M")
            != tramo.entrada.strftime("%H:%M")
            or _origen_registro_administrativo(entrada_original) != tramo.origen
        ):
            entrada_original.eliminado = True
            _crear_registro_editado(
                session,
                fichaje,
                "entrada",
                tramo.entrada,
                tramo.origen,
            )
            cambios += 1

        if tramo.salida is None:
            if salida_original is not None:
                salida_original.eliminado = True
                cambios += 1
        elif salida_original is None:
            _crear_registro_editado(
                session,
                fichaje,
                "salida",
                tramo.salida,
                tramo.origen,
            )
            cambios += 1
        elif (
            salida_original.timestamp.strftime("%H:%M")
            != tramo.salida.strftime("%H:%M")
            or _origen_registro_administrativo(salida_original) != tramo.origen
        ):
            origen_salida_anterior = _origen_registro_administrativo(
                salida_original
            )
            salida_original.eliminado = True
            _crear_registro_editado(
                session,
                fichaje,
                "salida",
                tramo.salida,
                tramo.origen,
            )
            cambios += 1
            if origen_salida_anterior != tramo.origen:
                _crear_auditoria_edicion(
                    session,
                    fichaje,
                    administrador_id,
                    "origen_salida",
                    origen_salida_anterior,
                    tramo.origen,
                    fecha_modificacion,
                )

        if entrada_original is None:
            _crear_auditoria_edicion(
                session,
                fichaje,
                administrador_id,
                "tramo_add",
                "-",
                f"ADD {nuevo}",
                fecha_modificacion,
            )
        elif salida_original is None and tramo.salida is not None:
            _crear_auditoria_edicion(
                session,
                fichaje,
                administrador_id,
                "entrada_abierta",
                anterior,
                nuevo,
                fecha_modificacion,
            )
        else:
            _crear_auditoria_edicion(
                session,
                fichaje,
                administrador_id,
                "tramo_mod",
                anterior,
                nuevo,
                fecha_modificacion,
            )

        if (
            entrada_original is not None
            and _origen_registro_administrativo(entrada_original) != tramo.origen
        ):
            _crear_auditoria_edicion(
                session,
                fichaje,
                administrador_id,
                "origen_mod",
                _origen_registro_administrativo(entrada_original),
                tramo.origen,
                fecha_modificacion,
            )

    for registro_id in solicitud.irregulares_a_eliminar:
        registro = registros[registro_id]
        registro.eliminado = True
        cambios += 1
        resumen = f"{registro.tipo[:10]}@{registro.timestamp.strftime('%H:%M')}"
        _crear_auditoria_edicion(
            session,
            fichaje,
            administrador_id,
            "incidencia_del",
            resumen,
            "DEL",
            fecha_modificacion,
        )

    return cambios


def editar_fichaje_administrativo(
    session,
    *,
    administrador_id,
    fichaje_id,
    entrada,
    secret_key,
) -> ResultadoEdicionFichajeAdministrativo:
    """Edita los tramos administrativos dentro de una única transacción.

    La sesión debe estar limpia. Tras localizar la cabecera se bloquea primero
    la fila estable del usuario; todas las lecturas usadas para decidir se
    repiten como lecturas actuales bajo ese bloqueo en MySQL/MariaDB.
    """

    usuario_id = None
    fecha_fichaje = None

    def omitir(codigo, *, mensaje=None):
        _rollback(session)
        return ResultadoEdicionFichajeAdministrativo(
            codigo=codigo,
            fichaje_id=fichaje_id if _identificador_positivo(fichaje_id) else None,
            usuario_id=usuario_id,
            fecha=fecha_fichaje,
            mensaje=mensaje,
        )

    if not _identificador_positivo(administrador_id):
        return omitir(ADMIN_EDICION_ADMINISTRADOR_INEXISTENTE)
    if not _identificador_positivo(fichaje_id):
        return omitir(ADMIN_EDICION_FICHAJE_INEXISTENTE)
    if not isinstance(entrada, EntradaEdicionFichajeAdministrativo):
        return omitir(
            ADMIN_EDICION_TRAMOS_INVALIDOS,
            mensaje="La solicitud de edición no es válida.",
        )

    try:
        referencia = session.execute(
            select(Fichaje.usuario_id).where(Fichaje.id == fichaje_id)
        ).one_or_none()
        if referencia is None:
            return omitir(ADMIN_EDICION_FICHAJE_INEXISTENTE)
        usuario_id = referencia.usuario_id

        usuario = _bloquear_usuario(session, usuario_id)
        if usuario is None:
            return omitir(ADMIN_EDICION_USUARIO_INEXISTENTE)

        fichaje = _consultar_fichaje_bajo_bloqueo(session, fichaje_id)
        if fichaje is None:
            return omitir(ADMIN_EDICION_FICHAJE_INEXISTENTE)
        if fichaje.usuario_id != usuario_id:
            return omitir(
                ADMIN_EDICION_CONFLICTO_CONCURRENTE,
                mensaje=(
                    "El fichaje fue modificado por otra operación. "
                    "Recarga la página."
                ),
            )
        fecha_fichaje = fichaje.fecha
        if fichaje.eliminado is True:
            return omitir(ADMIN_EDICION_FICHAJE_ELIMINADO)

        if administrador_id == usuario_id:
            administrador = usuario
        else:
            administrador = session.execute(
                select(Usuario)
                .where(Usuario.id == administrador_id)
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
        if administrador is None:
            return omitir(ADMIN_EDICION_ADMINISTRADOR_INEXISTENTE)
        if administrador.admin is not True:
            return omitir(ADMIN_EDICION_SIN_PERMISOS)

        fichaje_ids_activos = _consultar_ids_fichajes_activos_bajo_bloqueo(
            session,
            usuario_id,
            fecha_fichaje,
        )
        if len(fichaje_ids_activos) > 1:
            return omitir(ADMIN_EDICION_FICHAJES_ACTIVOS_MULTIPLES)
        if fichaje_ids_activos != [fichaje_id]:
            return omitir(ADMIN_EDICION_FICHAJE_ELIMINADO)

        registros_activos = _consultar_registros_activos(
            session,
            fichaje_id,
            bloquear=True,
        )
        try:
            validar_snapshot_firmado(
                entrada.snapshot,
                fichaje_id,
                registros_activos,
                secret_key,
            )
        except ErrorSnapshotEdicionFichaje as exc:
            return omitir(
                ADMIN_EDICION_CONFLICTO_CONCURRENTE,
                mensaje=str(exc),
            )

        preparacion = preparar_edicion(reconstruir_tramos(registros_activos))
        try:
            solicitud = parsear_y_validar_formulario(
                entrada.campos,
                preparacion,
                registros_activos,
            )
        except ErrorRegistroEdicionFichaje as exc:
            return omitir(
                ADMIN_EDICION_REGISTRO_AJENO,
                mensaje=str(exc),
            )
        except ErrorEdicionFichaje as exc:
            return omitir(
                ADMIN_EDICION_TRAMOS_INVALIDOS,
                mensaje=str(exc),
            )

        cambios = _aplicar_edicion_fichaje(
            session,
            fichaje,
            registros_activos,
            solicitud,
            administrador_id,
            ahora_madrid().replace(tzinfo=None, microsecond=0),
        )
        if cambios == 0:
            return omitir(ADMIN_EDICION_SIN_CAMBIOS)

        session.commit()
        return ResultadoEdicionFichajeAdministrativo(
            codigo=ADMIN_EDICION_ACTUALIZADA,
            fichaje_id=fichaje_id,
            usuario_id=usuario_id,
            fecha=fecha_fichaje,
        )
    except Exception as exc:
        codigo_db = _codigo_error_base_datos(exc)
        _rollback(session)
        if codigo_db == 1020:
            return ResultadoEdicionFichajeAdministrativo(
                codigo=ADMIN_EDICION_CONFLICTO_CONCURRENTE,
                fichaje_id=fichaje_id,
                usuario_id=usuario_id,
                fecha=fecha_fichaje,
                mensaje=(
                    "El fichaje fue modificado por otra operación. "
                    "Recarga la página."
                ),
            )
        return ResultadoEdicionFichajeAdministrativo(
            codigo=ADMIN_EDICION_ERROR_PERSISTENCIA,
            fichaje_id=fichaje_id,
            usuario_id=usuario_id,
            fecha=fecha_fichaje,
        )


def eliminar_fichaje_administrativo(
    session,
    *,
    administrador_id,
    fichaje_id,
    snapshot,
    secret_key,
) -> ResultadoBorradoFichajeAdministrativo:
    """Elimina lógicamente una cabecera dentro de una única transacción.

    La sesión recibida debe estar limpia. La operación conserva intactos todos
    los registros hijos y no crea ``Modificacion``, siguiendo la convención
    histórica. El ID solicitado identifica la única cabecera que puede cambiar,
    incluso si existen otras cabeceras activas para el mismo usuario y fecha.
    """

    usuario_id = None
    fecha_fichaje = None

    def omitir(codigo, *, mensaje=None):
        _rollback(session)
        return ResultadoBorradoFichajeAdministrativo(
            codigo=codigo,
            fichaje_id=fichaje_id if _identificador_positivo(fichaje_id) else None,
            usuario_id=usuario_id,
            fecha=fecha_fichaje,
            mensaje=mensaje,
        )

    if not _identificador_positivo(administrador_id):
        return omitir(ADMIN_BORRADO_ADMINISTRADOR_INEXISTENTE)
    if not _identificador_positivo(fichaje_id):
        return omitir(ADMIN_BORRADO_FICHAJE_INEXISTENTE)

    try:
        referencia = session.execute(
            select(Fichaje.usuario_id).where(Fichaje.id == fichaje_id)
        ).one_or_none()
        if referencia is None:
            return omitir(ADMIN_BORRADO_FICHAJE_INEXISTENTE)
        usuario_id = referencia.usuario_id

        usuario = _bloquear_usuario(session, usuario_id)
        if usuario is None:
            return omitir(ADMIN_BORRADO_USUARIO_INEXISTENTE)

        fichaje = _consultar_modelo_fichaje_bajo_bloqueo(session, fichaje_id)
        if fichaje is None:
            return omitir(ADMIN_BORRADO_FICHAJE_INEXISTENTE)
        if fichaje.usuario_id != usuario_id:
            return omitir(
                ADMIN_BORRADO_CONFLICTO_CONCURRENTE,
                mensaje=(
                    "El fichaje cambió durante la operación. Recarga la página."
                ),
            )
        fecha_fichaje = fichaje.fecha

        if administrador_id == usuario_id:
            administrador = usuario
        else:
            administrador = session.execute(
                select(Usuario)
                .where(Usuario.id == administrador_id)
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
        if administrador is None:
            return omitir(ADMIN_BORRADO_ADMINISTRADOR_INEXISTENTE)
        if administrador.admin is not True:
            return omitir(ADMIN_BORRADO_SIN_PERMISOS)

        if fichaje.eliminado is True:
            return omitir(ADMIN_BORRADO_YA_ELIMINADO)

        registros_activos = _consultar_registros_activos(
            session,
            fichaje_id,
            bloquear=True,
        )
        try:
            validar_snapshot_borrado_firmado(
                snapshot,
                fichaje,
                registros_activos,
                secret_key,
            )
        except ErrorSnapshotBorradoFichaje as exc:
            return omitir(
                ADMIN_BORRADO_CONFLICTO_CONCURRENTE,
                mensaje=str(exc),
            )

        fichaje.eliminado = True
        session.flush()
        session.commit()
        return ResultadoBorradoFichajeAdministrativo(
            codigo=ADMIN_BORRADO_ELIMINADO,
            fichaje_id=fichaje_id,
            usuario_id=usuario_id,
            fecha=fecha_fichaje,
        )
    except Exception as exc:
        codigo_db = _codigo_error_base_datos(exc)
        _rollback(session)
        if codigo_db == 1020:
            try:
                estado_actual = session.execute(
                    select(
                        Fichaje.usuario_id,
                        Fichaje.fecha,
                        Fichaje.eliminado,
                    ).where(Fichaje.id == fichaje_id)
                ).one_or_none()
            except Exception:
                _rollback(session)
            else:
                if estado_actual is not None:
                    usuario_id = estado_actual.usuario_id
                    fecha_fichaje = estado_actual.fecha
                    codigo = (
                        ADMIN_BORRADO_YA_ELIMINADO
                        if estado_actual.eliminado is True
                        else ADMIN_BORRADO_CONFLICTO_CONCURRENTE
                    )
                    return omitir(
                        codigo,
                        mensaje=(
                            "El fichaje cambió durante la operación. "
                            "Recarga la página."
                        ),
                    )
        return ResultadoBorradoFichajeAdministrativo(
            codigo=ADMIN_BORRADO_ERROR_PERSISTENCIA,
            fichaje_id=fichaje_id,
            usuario_id=usuario_id,
            fecha=fecha_fichaje,
        )


def obtener_entrada_abierta_para_autofichaje(session, usuario_id, fecha):
    """Lectura orientativa para planificar; la escritura revalida bajo lock."""
    fichajes = _consultar_fichajes_activos(session, usuario_id, fecha)
    if len(fichajes) > 1:
        raise ErrorRegistroFichaje(FICHAJES_ACTIVOS_MULTIPLES)
    if not fichajes:
        return None
    registros = _consultar_registros_activos(session, fichajes[0].id)
    return analizar_secuencia(registros, fecha).entrada_abierta


def registrar_salida_automatica(
    session,
    usuario_id: int,
    instante_efectivo,
) -> ResultadoSalidaAutomatica:
    """Cierra de forma idempotente un tramo mediante una salida de sistema.

    La sesión recibida debe estar limpia: esta operación es propietaria de la
    transacción completa y siempre ejecuta ``commit`` o ``rollback``.
    """
    try:
        instante = _instante_madrid_segundos(instante_efectivo)
    except (AttributeError, TypeError, ValueError):
        _rollback(session)
        return ResultadoSalidaAutomatica(AUTO_TIMESTAMP_INVALIDO, None, None)

    fecha = instante.date()

    def omitir(codigo):
        _rollback(session)
        return ResultadoSalidaAutomatica(codigo, instante, fecha)

    try:
        usuario = _bloquear_usuario(session, usuario_id)
        if usuario is None:
            return omitir(AUTO_USUARIO_INEXISTENTE)

        ausencias = _consultar_ausencias(session, usuario_id, fecha)
        if existe_ausencia_bloqueante(ausencias, fecha):
            return omitir(AUTO_AUSENCIA_BLOQUEANTE)

        fichajes = _consultar_fichajes_activos(session, usuario_id, fecha)
        if not fichajes:
            return omitir(AUTO_SIN_FICHAJE_ACTIVO)
        if len(fichajes) > 1:
            return omitir(AUTO_FICHAJES_ACTIVOS_MULTIPLES)

        fichaje = fichajes[0]
        registros = _consultar_registros_activos(session, fichaje.id)
        if not registros:
            return omitir(AUTO_SIN_TRAMO_ABIERTO)

        try:
            estado = analizar_secuencia(registros, fecha)
        except ErrorRegistroFichaje:
            return omitir(AUTO_SECUENCIA_ANOMALA)

        if estado.entrada_abierta is None:
            return omitir(AUTO_YA_CERRADO)

        actual = _instante_local_sin_zona(instante, instante.tzinfo)
        ultima_entrada = _instante_local_sin_zona(
            estado.entrada_abierta.timestamp,
            instante.tzinfo,
        )
        ultimo_registro = _instante_local_sin_zona(
            registros[-1].timestamp,
            instante.tzinfo,
        )
        if actual <= ultima_entrada or actual <= ultimo_registro:
            return omitir(AUTO_TIMESTAMP_INVALIDO)

        session.add(
            RegistroHorario(
                fichaje_id=fichaje.id,
                tipo="salida",
                timestamp=instante,
                creado_por_admin=True,
                eliminado=False,
                origen="Auto",
            )
        )
        session.commit()
        return ResultadoSalidaAutomatica(AUTO_SALIDA_CREADA, instante, fecha)
    except Exception:
        _rollback(session)
        return ResultadoSalidaAutomatica(AUTO_ERROR_PERSISTENCIA, instante, fecha)


def registrar_fichaje_usuario(
    session,
    usuario_id: int,
    tipo,
    origen=None,
    *,
    ahora=None,
) -> ResultadoRegistroFichaje:
    """Registra una acción normal en una sola transacción y un solo commit.

    En MySQL/MariaDB se bloquea primero la fila estable del usuario. Así se
    serializan todas las solicitudes del mismo usuario aunque aún no exista la
    cabecera diaria. SQLite omite el bloqueo y conserva compatibilidad de tests.
    """
    etapa = "validacion"
    try:
        instante_proporcionado = ahora is not None
        tipo_normalizado = normalizar_tipo(tipo)
        origen_normalizado = (
            normalizar_origen_usuario(origen)
            if tipo_normalizado == "entrada"
            else None
        )
        instante = _instante_madrid_segundos(ahora)
        fecha = instante.date()

        etapa = "bloqueo_usuario"
        usuario = _bloquear_usuario(session, usuario_id)
        if usuario is None:
            raise ErrorRegistroFichaje(USUARIO_NO_ENCONTRADO)

        etapa = "consulta_ausencias"
        ausencias = _consultar_ausencias(session, usuario_id, fecha)
        if existe_ausencia_bloqueante(ausencias, fecha):
            bloqueante = next(
                ausencia
                for ausencia in ausencias
                if existe_ausencia_bloqueante((ausencia,), fecha)
            )
            raise ErrorRegistroFichaje(
                AUSENCIA_BLOQUEANTE,
                detalle=bloqueante.tipo,
            )

        etapa = "consulta_fichajes"
        fichajes = _consultar_fichajes_activos(session, usuario_id, fecha)
        if len(fichajes) > 1:
            raise ErrorRegistroFichaje(FICHAJES_ACTIVOS_MULTIPLES)

        fichaje = fichajes[0] if fichajes else None
        registros = []
        if fichaje is None:
            if tipo_normalizado == "salida":
                raise ErrorRegistroFichaje(SALIDA_SIN_ENTRADA)
            fichaje = Fichaje(
                usuario_id=usuario_id,
                fecha=fecha,
                fecha_creacion=instante,
                creado_por_admin=False,
                eliminado=False,
            )
            session.add(fichaje)
            session.flush()
            estado = EstadoSecuencia("entrada", None)
        else:
            etapa = "consulta_registros"
            registros = _consultar_registros_activos(session, fichaje.id)
            etapa = "analisis_secuencia"
            estado = analizar_secuencia(registros, fecha)

        if tipo_normalizado != estado.siguiente_tipo:
            if tipo_normalizado == "entrada":
                raise ErrorRegistroFichaje(ENTRADA_DUPLICADA)
            codigo = SALIDA_DUPLICADA if registros else SALIDA_SIN_ENTRADA
            raise ErrorRegistroFichaje(codigo)

        if registros:
            etapa = "validacion_instante"
            ultimo = _instante_local_sin_zona(
                registros[-1].timestamp,
                instante.tzinfo,
            )
            actual = _instante_local_sin_zona(instante, instante.tzinfo)
            if actual <= ultimo and not instante_proporcionado:
                instante = instante + (ultimo - actual) + timedelta(seconds=1)
                actual = _instante_local_sin_zona(instante, instante.tzinfo)
            if actual <= ultimo or instante.date() != fecha:
                raise ErrorRegistroFichaje(SECUENCIA_ANOMALA)

        if tipo_normalizado == "salida":
            etapa = "validacion_origen_historico"
            origen_normalizado = _normalizar_origen_historico(
                estado.entrada_abierta.origen
            )

        etapa = "alta_registro"
        session.add(
            RegistroHorario(
                fichaje_id=fichaje.id,
                tipo=tipo_normalizado,
                timestamp=instante,
                creado_por_admin=False,
                eliminado=False,
                origen=origen_normalizado,
            )
        )
        etapa = "commit"
        session.commit()
        return ResultadoRegistroFichaje(
            codigo=OK_ENTRADA if tipo_normalizado == "entrada" else OK_SALIDA,
            tipo=tipo_normalizado,
            origen=origen_normalizado,
            instante=instante,
            fecha=fecha,
        )
    except ErrorRegistroFichaje as exc:
        _rollback(session)
        if exc.codigo in {SECUENCIA_ANOMALA, FICHAJES_ACTIVOS_MULTIPLES}:
            logging.warning(
                "Fichaje normal rechazado (codigo=%s, etapa=%s).",
                exc.codigo,
                etapa,
            )
        raise
    except Exception as exc:
        _rollback(session)
        codigo_db = _codigo_error_base_datos(exc)
        logging.error(
            "Error técnico al persistir fichaje (%s, db_code=%s, etapa=%s).",
            type(exc).__name__,
            codigo_db,
            etapa,
        )
        raise ErrorRegistroFichaje(ERROR_PERSISTENCIA) from exc
