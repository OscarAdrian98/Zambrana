"""Reglas reutilizables para ausencias almacenadas como una fila por día."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
import unicodedata

from itsdangerous import BadSignature, URLSafeSerializer
import pytz
from sqlalchemy import select

from app import db
from app.models import Ausencia, Usuario


TIPO_VACACIONES = "Vacaciones"
TIPO_ENFERMEDAD = "Enfermedad"
TIPO_ASUNTOS_PROPIOS = "Asuntos propios"
TIPO_BAJA = "Baja"
TIPO_MEDICO = "Medico"

TIPOS_AUSENCIA = (
    TIPO_VACACIONES,
    TIPO_ENFERMEDAD,
    TIPO_ASUNTOS_PROPIOS,
    TIPO_BAJA,
    TIPO_MEDICO,
)

LONGITUD_MAXIMA_TIPO = 50
LONGITUD_MAXIMA_OBSERVACIONES = 255
ZONA_MADRID = pytz.timezone("Europe/Madrid")
_PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PATRON_HORA = re.compile(r"^\d{2}:\d{2}$")
_PATRON_IDS = re.compile(r"^[1-9]\d*(?:,[1-9]\d*)*$")
_SAL_SNAPSHOT_AUSENCIA = "gestion-ausencia-usuario-v1"

AUSENCIA_CREADA = "ausencia_creada"
AUSENCIA_ACTUALIZADA = "ausencia_actualizada"
AUSENCIA_ELIMINADA = "ausencia_eliminada"
AUSENCIA_DUPLICADA = "ausencia_duplicada"
AUSENCIA_SIN_CAMBIOS = "ausencia_sin_cambios"
AUSENCIA_CONFLICTO_CONCURRENTE = "ausencia_conflicto_concurrente"
AUSENCIA_DATOS_INVALIDOS = "ausencia_datos_invalidos"
AUSENCIA_USUARIO_INEXISTENTE = "ausencia_usuario_inexistente"
AUSENCIA_ADMINISTRADOR_INEXISTENTE = "ausencia_administrador_inexistente"
AUSENCIA_SIN_PERMISOS = "ausencia_sin_permisos"
AUSENCIA_BLOQUE_INEXISTENTE = "ausencia_bloque_inexistente"
AUSENCIA_BLOQUE_AJENO = "ausencia_bloque_ajeno"
AUSENCIA_SNAPSHOT_INVALIDO = "ausencia_snapshot_invalido"
AUSENCIA_ERROR_PERSISTENCIA = "ausencia_error_persistencia"


class ErrorValidacionAusencia(ValueError):
    """Entrada inválida que puede comunicarse sin revelar detalles internos."""


@dataclass(frozen=True)
class EntradaAusencia:
    fecha_desde: str | None
    fecha_hasta: str | None
    tipo: str | None
    observaciones: str | None = None
    hora_desde: str | None = None
    hora_hasta: str | None = None


@dataclass(frozen=True)
class EntradaEdicionAusencia:
    snapshot: str
    fecha_desde: str | None
    fecha_hasta: str | None
    tipo: str | None
    observaciones: str | None = None
    hora_desde: str | None = None
    hora_hasta: str | None = None


@dataclass(frozen=True)
class ResultadoAusencia:
    codigo: str
    cantidad: int = 0
    ids: tuple[int, ...] = ()
    mensaje: str | None = None
    edicion: dict | None = None


@dataclass(frozen=True)
class DatosAusencia:
    fecha_desde: date
    fecha_hasta: date
    tipo: str
    observaciones: str | None
    hora_desde: time | None
    hora_hasta: time | None

    @property
    def fechas(self):
        return fechas_intervalo(self.fecha_desde, self.fecha_hasta)


def _sin_tildes_minusculas(valor):
    normalizado = unicodedata.normalize("NFKD", valor.strip().lower())
    sin_tildes = "".join(
        caracter
        for caracter in normalizado
        if not unicodedata.combining(caracter)
    )
    return " ".join(sin_tildes.split())


_TIPOS_POR_CLAVE = {
    _sin_tildes_minusculas(tipo): tipo for tipo in TIPOS_AUSENCIA
}


def normalizar_tipo_ausencia(valor):
    if not isinstance(valor, str):
        raise ErrorValidacionAusencia("Selecciona un tipo de ausencia válido.")
    if len(valor) > LONGITUD_MAXIMA_TIPO:
        raise ErrorValidacionAusencia("Selecciona un tipo de ausencia válido.")
    if any(
        unicodedata.category(caracter).startswith("C") for caracter in valor
    ):
        raise ErrorValidacionAusencia("Selecciona un tipo de ausencia válido.")

    tipo = _TIPOS_POR_CLAVE.get(_sin_tildes_minusculas(valor))
    if tipo is None:
        raise ErrorValidacionAusencia("Selecciona un tipo de ausencia válido.")
    return tipo


def tipo_canonico_existente(valor):
    """Canoniza aliases históricos conocidos sin rechazar un valor desconocido."""
    if not isinstance(valor, str):
        return ""
    return _TIPOS_POR_CLAVE.get(_sin_tildes_minusculas(valor), valor.strip())


def es_ausencia_medica(valor):
    tipo = getattr(valor, "tipo", valor)
    return _sin_tildes_minusculas(str(tipo or "")) == "medico"


def ausencia_bloquea_fichaje(valor):
    return bool(valor) and not es_ausencia_medica(valor)


def seleccionar_ausencia_bloqueante(ausencias):
    for ausencia in sorted(ausencias, key=lambda item: item.id):
        if ausencia_bloquea_fichaje(ausencia):
            return ausencia
    return None


def parsear_fecha(valor, nombre):
    if not isinstance(valor, str) or not valor:
        raise ErrorValidacionAusencia(f"La fecha {nombre} es obligatoria.")
    if len(valor) != 10 or not _PATRON_FECHA.fullmatch(valor):
        raise ErrorValidacionAusencia(f"La fecha {nombre} no es válida.")
    try:
        return date.fromisoformat(valor)
    except ValueError as error:
        raise ErrorValidacionAusencia(
            f"La fecha {nombre} no es válida."
        ) from error


def validar_fechas(fecha_desde, fecha_hasta):
    desde = parsear_fecha(fecha_desde, "inicial")
    hasta = parsear_fecha(fecha_hasta, "final")
    if hasta < desde:
        raise ErrorValidacionAusencia(
            'La fecha "Hasta" no puede ser anterior a "Desde".'
        )
    return desde, hasta


def _parsear_hora(valor, nombre):
    if not isinstance(valor, str) or not _PATRON_HORA.fullmatch(valor):
        raise ErrorValidacionAusencia(f"La hora {nombre} no es válida.")
    try:
        return datetime.strptime(valor, "%H:%M").time()
    except ValueError as error:
        raise ErrorValidacionAusencia(
            f"La hora {nombre} no es válida."
        ) from error


def validar_horas_medicas(tipo, hora_desde, hora_hasta):
    if not es_ausencia_medica(tipo):
        return None, None

    desde_vacia = hora_desde in (None, "")
    hasta_vacia = hora_hasta in (None, "")
    if desde_vacia and hasta_vacia:
        return None, None
    if desde_vacia != hasta_vacia:
        raise ErrorValidacionAusencia(
            "Debes indicar ambas horas de la cita médica."
        )

    desde = _parsear_hora(hora_desde, "inicial")
    hasta = _parsear_hora(hora_hasta, "final")
    if hasta <= desde:
        raise ErrorValidacionAusencia(
            "La hora final debe ser posterior a la hora inicial."
        )
    return desde, hasta


def normalizar_observaciones(valor):
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise ErrorValidacionAusencia("Las observaciones no son válidas.")
    if any(
        unicodedata.category(caracter).startswith("C") for caracter in valor
    ):
        raise ErrorValidacionAusencia("Las observaciones no son válidas.")

    observaciones = valor.strip()
    if len(observaciones) > LONGITUD_MAXIMA_OBSERVACIONES:
        raise ErrorValidacionAusencia(
            "Las observaciones no pueden superar "
            f"{LONGITUD_MAXIMA_OBSERVACIONES} caracteres."
        )
    return observaciones or None


def preparar_datos_ausencia(formulario):
    fecha_desde, fecha_hasta = validar_fechas(
        formulario.get("fecha_desde"),
        formulario.get("fecha_hasta"),
    )
    tipo = normalizar_tipo_ausencia(formulario.get("tipo"))
    observaciones = normalizar_observaciones(
        formulario.get("observaciones", "")
    )
    hora_desde, hora_hasta = validar_horas_medicas(
        tipo,
        formulario.get("hora_desde"),
        formulario.get("hora_hasta"),
    )
    return DatosAusencia(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        tipo=tipo,
        observaciones=observaciones,
        hora_desde=hora_desde,
        hora_hasta=hora_hasta,
    )


def preparar_entrada_ausencia(entrada):
    fecha_desde, fecha_hasta = validar_fechas(
        entrada.fecha_desde,
        entrada.fecha_hasta,
    )
    tipo = normalizar_tipo_ausencia(entrada.tipo)
    observaciones = normalizar_observaciones(entrada.observaciones)
    hora_desde, hora_hasta = validar_horas_medicas(
        tipo,
        entrada.hora_desde,
        entrada.hora_hasta,
    )
    return DatosAusencia(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        tipo=tipo,
        observaciones=observaciones,
        hora_desde=hora_desde,
        hora_hasta=hora_hasta,
    )


def fechas_intervalo(fecha_desde, fecha_hasta):
    return tuple(
        fecha_desde + timedelta(days=desplazamiento)
        for desplazamiento in range((fecha_hasta - fecha_desde).days + 1)
    )


def calcular_dias_consumidos(fecha_desde, fecha_hasta):
    """Preserva el cómputo actual: todos los días naturales, ambos incluidos."""
    if fecha_hasta < fecha_desde:
        raise ErrorValidacionAusencia("El intervalo de fechas no es válido.")
    return (fecha_hasta - fecha_desde).days + 1


def ausencia_cubre_fecha(ausencia, fecha):
    return ausencia.fecha == fecha


def existe_ausencia_bloqueante(ausencias, fecha):
    """Decide por todas las filas del día, sin depender de su orden."""
    return any(
        ausencia_cubre_fecha(ausencia, fecha)
        and ausencia_bloquea_fichaje(ausencia)
        for ausencia in ausencias
    )


def agrupar_ausencias_por_usuario(ausencias, fecha):
    """Agrupa solo las ausencias de la fecha local que se está evaluando."""
    agrupadas = {}
    for ausencia in ausencias:
        if not ausencia_cubre_fecha(ausencia, fecha):
            continue
        agrupadas.setdefault(ausencia.usuario_id, []).append(ausencia)
    return agrupadas


def usuarios_con_ausencia_bloqueante(ausencias, fecha):
    return {
        usuario_id
        for usuario_id, filas in agrupar_ausencias_por_usuario(
            ausencias,
            fecha,
        ).items()
        if existe_ausencia_bloqueante(filas, fecha)
    }


def _observaciones_existentes(ausencia):
    return (ausencia.observaciones or "").strip() or None


def buscar_duplicados_exactos(ausencias, datos, excluir_ids=()):
    ids_excluidos = set(excluir_ids)
    fechas = set(datos.fechas)
    return [
        ausencia
        for ausencia in ausencias
        if ausencia.id not in ids_excluidos
        and ausencia.fecha in fechas
        and tipo_canonico_existente(ausencia.tipo) == datos.tipo
        and _observaciones_existentes(ausencia) == datos.observaciones
        and ausencia.hora_desde == datos.hora_desde
        and ausencia.hora_hasta == datos.hora_hasta
    ]


def puede_gestionar_ausencia(usuario, ausencia):
    return bool(usuario.admin) or ausencia.usuario_id == usuario.id


def parsear_ids_ausencias(valor):
    if not isinstance(valor, str) or not _PATRON_IDS.fullmatch(valor):
        raise ErrorValidacionAusencia("La ausencia indicada no es válida.")
    ids = tuple(dict.fromkeys(int(item) for item in valor.split(",")))
    if not ids:
        raise ErrorValidacionAusencia("La ausencia indicada no es válida.")
    return ids


def agrupar_ausencias(ausencias, hoy):
    grupos = {}
    for ausencia in ausencias:
        clave = (
            tipo_canonico_existente(ausencia.tipo),
            _observaciones_existentes(ausencia),
            ausencia.hora_desde,
            ausencia.hora_hasta,
        )
        grupos.setdefault(clave, []).append(ausencia)

    bloques = []
    for (tipo, observaciones, hora_desde, hora_hasta), filas in grupos.items():
        filas = sorted(filas, key=lambda item: (item.fecha, item.id))
        bloque = []
        for ausencia in filas:
            if bloque and (ausencia.fecha - bloque[-1].fecha).days != 1:
                bloques.append(
                    _crear_bloque(
                        bloque,
                        tipo,
                        observaciones,
                        hora_desde,
                        hora_hasta,
                        hoy,
                    )
                )
                bloque = []
            bloque.append(ausencia)
        if bloque:
            bloques.append(
                _crear_bloque(
                    bloque,
                    tipo,
                    observaciones,
                    hora_desde,
                    hora_hasta,
                    hoy,
                )
            )
    return sorted(bloques, key=lambda item: item["fecha"], reverse=True)


def _crear_bloque(
    filas,
    tipo,
    observaciones,
    hora_desde,
    hora_hasta,
    hoy,
):
    return {
        "ids": tuple(item.id for item in filas),
        "ids_texto": ",".join(str(item.id) for item in filas),
        "fecha": filas[0].fecha,
        "fecha_hasta": filas[-1].fecha,
        "tipo": tipo,
        "observaciones": observaciones,
        "estado": "utilizadas" if filas[-1].fecha < hoy else "pendiente",
        "dias": len(filas),
        "creado_por_admin": any(
            bool(item.creado_por_admin) for item in filas
        ),
        "hora_desde": hora_desde,
        "hora_hasta": hora_hasta,
    }


def calcular_saldo_vacaciones(ausencias, hoy, total_anual=30):
    bloques = agrupar_ausencias(ausencias, hoy)
    utilizadas = [
        bloque
        for bloque in bloques
        if bloque["tipo"] == TIPO_VACACIONES
        and bloque["fecha_hasta"] < hoy
    ]
    solicitadas = [
        bloque
        for bloque in bloques
        if bloque["tipo"] == TIPO_VACACIONES and bloque["fecha"] >= hoy
    ]
    saldo_utilizado = sum(bloque["dias"] for bloque in utilizadas)
    saldo_solicitado = sum(bloque["dias"] for bloque in solicitadas)
    return {
        "saldo_utilizado": saldo_utilizado,
        "saldo_solicitado": saldo_solicitado,
        "saldo_disponible": total_anual
        - saldo_utilizado
        - saldo_solicitado,
    }


def ahora_madrid(ahora=None):
    if ahora is None:
        return datetime.now(ZONA_MADRID)
    if ahora.tzinfo is None:
        raise ValueError("La fecha de referencia debe incluir zona horaria.")
    return ahora.astimezone(ZONA_MADRID)


def fecha_hoy_madrid(ahora=None):
    return ahora_madrid(ahora).date()


def _valor_hora_snapshot(valor):
    return valor.isoformat(timespec="minutes") if valor is not None else None


def _datos_snapshot_ausencia(usuario_id, ausencias):
    filas = sorted(ausencias, key=lambda item: (item.fecha, item.id))
    return {
        "usuario_id": int(usuario_id),
        "filas": [
            [
                int(ausencia.id),
                int(ausencia.usuario_id),
                ausencia.fecha.isoformat(),
                ausencia.tipo,
                (ausencia.observaciones or "").strip() or None,
                _valor_hora_snapshot(ausencia.hora_desde),
                _valor_hora_snapshot(ausencia.hora_hasta),
                bool(ausencia.creado_por_admin),
            ]
            for ausencia in filas
        ],
    }


def crear_snapshot_ausencia_firmado(usuario_id, ausencias, secret_key):
    if not secret_key:
        raise ValueError("La clave de firma de ausencias es obligatoria.")
    serializer = URLSafeSerializer(
        secret_key,
        salt=_SAL_SNAPSHOT_AUSENCIA,
    )
    return serializer.dumps(_datos_snapshot_ausencia(usuario_id, ausencias))


def _cargar_snapshot_ausencia(token, secret_key):
    if not token or not secret_key:
        raise ErrorValidacionAusencia("La huella de ausencia no es válida.")
    serializer = URLSafeSerializer(
        secret_key,
        salt=_SAL_SNAPSHOT_AUSENCIA,
    )
    try:
        datos = serializer.loads(token)
    except BadSignature as error:
        raise ErrorValidacionAusencia(
            "La huella de ausencia no es válida."
        ) from error
    if (
        not isinstance(datos, dict)
        or not isinstance(datos.get("usuario_id"), int)
        or not isinstance(datos.get("filas"), list)
        or not datos["filas"]
        or any(
            not isinstance(fila, list)
            or len(fila) != 8
            or not isinstance(fila[0], int)
            or not isinstance(fila[1], int)
            for fila in datos["filas"]
        )
    ):
        raise ErrorValidacionAusencia("La huella de ausencia no es válida.")
    ids = tuple(fila[0] for fila in datos["filas"])
    if len(ids) != len(set(ids)):
        raise ErrorValidacionAusencia("La huella de ausencia no es válida.")
    return datos


def _rollback(session):
    try:
        session.rollback()
    except Exception:
        pass


def _resultado_y_liberar(session, codigo, **campos):
    _rollback(session)
    return ResultadoAusencia(codigo=codigo, **campos)


def _bloquear_usuario(session, usuario_id):
    consulta = (
        select(Usuario)
        .where(Usuario.id == usuario_id)
        .execution_options(populate_existing=True)
    )
    dialecto = session.get_bind().dialect.name
    if dialecto in {"mysql", "mariadb"}:
        consulta = consulta.with_for_update()
    return session.execute(consulta).scalar_one_or_none()


def _ausencias_usuario(session, usuario_id):
    return tuple(
        session.execute(
            select(Ausencia)
            .where(Ausencia.usuario_id == usuario_id)
            .order_by(Ausencia.fecha, Ausencia.id)
        ).scalars()
    )


def _ausencias_intervalo(session, usuario_id, datos):
    return tuple(
        session.execute(
            select(Ausencia)
            .where(
                Ausencia.usuario_id == usuario_id,
                Ausencia.fecha >= datos.fecha_desde,
                Ausencia.fecha <= datos.fecha_hasta,
            )
            .order_by(Ausencia.fecha, Ausencia.id)
        ).scalars()
    )


def _crear_filas(usuario_id, datos, creado_por_admin):
    return tuple(
        Ausencia(
            usuario_id=usuario_id,
            fecha=fecha,
            tipo=datos.tipo,
            observaciones=datos.observaciones,
            hora_desde=datos.hora_desde,
            hora_hasta=datos.hora_hasta,
            creado_por_admin=creado_por_admin,
        )
        for fecha in datos.fechas
    )


def _persistir_nuevas(session, filas):
    for fila in filas:
        session.add(fila)
    session.commit()
    return tuple(int(fila.id) for fila in filas)


def _preparar_datos_controlados(entrada):
    try:
        return preparar_entrada_ausencia(entrada), None
    except ErrorValidacionAusencia as error:
        return None, ResultadoAusencia(
            codigo=AUSENCIA_DATOS_INVALIDOS,
            mensaje=str(error),
        )


def crear_ausencia_usuario(
    *,
    usuario_id,
    entrada,
    session=None,
):
    session = db.session if session is None else session
    datos, error = _preparar_datos_controlados(entrada)
    if error is not None:
        return error

    try:
        usuario = _bloquear_usuario(session, usuario_id)
        if usuario is None:
            return _resultado_y_liberar(
                session,
                AUSENCIA_USUARIO_INEXISTENTE,
            )
        existentes = _ausencias_intervalo(session, usuario_id, datos)
        if buscar_duplicados_exactos(existentes, datos):
            return _resultado_y_liberar(session, AUSENCIA_DUPLICADA)
        filas = _crear_filas(usuario_id, datos, creado_por_admin=False)
        ids = _persistir_nuevas(session, filas)
        return ResultadoAusencia(
            codigo=AUSENCIA_CREADA,
            cantidad=len(filas),
            ids=ids,
        )
    except Exception:
        _rollback(session)
        return ResultadoAusencia(codigo=AUSENCIA_ERROR_PERSISTENCIA)


def crear_ausencia_administrativa(
    *,
    administrador_id,
    usuario_id,
    entrada,
    session=None,
):
    session = db.session if session is None else session
    datos, error = _preparar_datos_controlados(entrada)
    if error is not None:
        return error

    try:
        usuario = _bloquear_usuario(session, usuario_id)
        if usuario is None:
            return _resultado_y_liberar(
                session,
                AUSENCIA_USUARIO_INEXISTENTE,
            )
        administrador = session.execute(
            select(Usuario).where(Usuario.id == administrador_id)
        ).scalar_one_or_none()
        if administrador is None:
            return _resultado_y_liberar(
                session,
                AUSENCIA_ADMINISTRADOR_INEXISTENTE,
            )
        if not administrador.admin:
            return _resultado_y_liberar(session, AUSENCIA_SIN_PERMISOS)
        existentes = _ausencias_intervalo(session, usuario_id, datos)
        if buscar_duplicados_exactos(existentes, datos):
            return _resultado_y_liberar(session, AUSENCIA_DUPLICADA)
        filas = _crear_filas(usuario_id, datos, creado_por_admin=True)
        ids = _persistir_nuevas(session, filas)
        return ResultadoAusencia(
            codigo=AUSENCIA_CREADA,
            cantidad=len(filas),
            ids=ids,
        )
    except Exception:
        _rollback(session)
        return ResultadoAusencia(codigo=AUSENCIA_ERROR_PERSISTENCIA)


def _filas_snapshot_bajo_lock(
    session,
    *,
    usuario_id,
    snapshot,
    secret_key,
    codigo_si_no_existe=AUSENCIA_BLOQUE_INEXISTENTE,
):
    try:
        esperado = _cargar_snapshot_ausencia(snapshot, secret_key)
    except ErrorValidacionAusencia:
        return None, None, ResultadoAusencia(
            codigo=AUSENCIA_SNAPSHOT_INVALIDO,
        )
    if esperado["usuario_id"] != usuario_id:
        return None, None, ResultadoAusencia(codigo=AUSENCIA_BLOQUE_AJENO)

    usuario = _bloquear_usuario(session, usuario_id)
    if usuario is None:
        return None, None, _resultado_y_liberar(
            session,
            AUSENCIA_USUARIO_INEXISTENTE,
        )

    todas = _ausencias_usuario(session, usuario_id)
    ids = tuple(fila[0] for fila in esperado["filas"])
    por_id = {ausencia.id: ausencia for ausencia in todas}
    presentes = tuple(por_id[item] for item in ids if item in por_id)
    if not presentes:
        return None, None, _resultado_y_liberar(
            session,
            codigo_si_no_existe,
        )
    if len(presentes) != len(ids):
        return None, None, _resultado_y_liberar(
            session,
            AUSENCIA_CONFLICTO_CONCURRENTE,
        )

    bloques = agrupar_ausencias(todas, fecha_hoy_madrid())
    coincidentes = [
        bloque
        for bloque in bloques
        if set(bloque["ids"]).intersection(ids)
    ]
    if (
        len(coincidentes) != 1
        or set(coincidentes[0]["ids"]) != set(ids)
        or _datos_snapshot_ausencia(usuario_id, presentes) != esperado
    ):
        return None, None, _resultado_y_liberar(
            session,
            AUSENCIA_CONFLICTO_CONCURRENTE,
        )
    return presentes, todas, None


def _filas_editables_por_empleado(filas):
    hoy = fecha_hoy_madrid()
    return not any(
        ausencia.creado_por_admin or ausencia.fecha < hoy
        for ausencia in filas
    )


def _datos_equivalentes(filas, datos):
    if len(filas) != len(datos.fechas):
        return False
    for ausencia, fecha in zip(
        sorted(filas, key=lambda item: (item.fecha, item.id)),
        datos.fechas,
    ):
        if (
            ausencia.fecha != fecha
            or tipo_canonico_existente(ausencia.tipo) != datos.tipo
            or _observaciones_existentes(ausencia) != datos.observaciones
            or ausencia.hora_desde != datos.hora_desde
            or ausencia.hora_hasta != datos.hora_hasta
            or bool(ausencia.creado_por_admin)
        ):
            return False
    return True


def preparar_edicion_ausencia_usuario(
    *,
    usuario_id,
    snapshot,
    secret_key,
    session=None,
):
    session = db.session if session is None else session
    try:
        esperado = _cargar_snapshot_ausencia(snapshot, secret_key)
    except ErrorValidacionAusencia:
        return ResultadoAusencia(codigo=AUSENCIA_SNAPSHOT_INVALIDO)
    if esperado["usuario_id"] != usuario_id:
        return ResultadoAusencia(codigo=AUSENCIA_BLOQUE_AJENO)

    ids = tuple(fila[0] for fila in esperado["filas"])
    todas = _ausencias_usuario(session, usuario_id)
    por_id = {ausencia.id: ausencia for ausencia in todas}
    filas = tuple(por_id[item] for item in ids if item in por_id)
    if len(filas) != len(ids):
        return ResultadoAusencia(codigo=AUSENCIA_BLOQUE_INEXISTENTE)
    bloques = agrupar_ausencias(todas, fecha_hoy_madrid())
    coincidentes = [
        bloque
        for bloque in bloques
        if set(bloque["ids"]).intersection(ids)
    ]
    if (
        len(coincidentes) != 1
        or set(coincidentes[0]["ids"]) != set(ids)
        or _datos_snapshot_ausencia(usuario_id, filas) != esperado
    ):
        return ResultadoAusencia(codigo=AUSENCIA_CONFLICTO_CONCURRENTE)
    if not _filas_editables_por_empleado(filas):
        return ResultadoAusencia(codigo=AUSENCIA_SIN_PERMISOS)

    bloque = coincidentes[0]
    return ResultadoAusencia(
        codigo=AUSENCIA_ACTUALIZADA,
        cantidad=len(filas),
        ids=ids,
        edicion={
            "snapshot": snapshot,
            "fecha_inicio": bloque["fecha"].isoformat(),
            "fecha_fin": bloque["fecha_hasta"].isoformat(),
            "tipo": bloque["tipo"],
            "observaciones": bloque["observaciones"] or "",
            "hora_desde": (
                bloque["hora_desde"].strftime("%H:%M")
                if bloque["hora_desde"]
                else ""
            ),
            "hora_hasta": (
                bloque["hora_hasta"].strftime("%H:%M")
                if bloque["hora_hasta"]
                else ""
            ),
        },
    )


def editar_ausencia_usuario(
    *,
    usuario_id,
    entrada,
    secret_key,
    session=None,
):
    session = db.session if session is None else session
    datos, error = _preparar_datos_controlados(entrada)
    if error is not None:
        return error

    try:
        filas, todas, error = _filas_snapshot_bajo_lock(
            session,
            usuario_id=usuario_id,
            snapshot=entrada.snapshot,
            secret_key=secret_key,
            codigo_si_no_existe=AUSENCIA_CONFLICTO_CONCURRENTE,
        )
        if error is not None:
            return error
        if not _filas_editables_por_empleado(filas):
            return _resultado_y_liberar(session, AUSENCIA_SIN_PERMISOS)
        if _datos_equivalentes(filas, datos):
            return _resultado_y_liberar(session, AUSENCIA_SIN_CAMBIOS)
        if buscar_duplicados_exactos(
            todas,
            datos,
            excluir_ids=tuple(item.id for item in filas),
        ):
            return _resultado_y_liberar(session, AUSENCIA_DUPLICADA)

        for ausencia in filas:
            session.delete(ausencia)
        session.flush()
        nuevas = _crear_filas(
            usuario_id,
            datos,
            creado_por_admin=False,
        )
        ids = _persistir_nuevas(session, nuevas)
        return ResultadoAusencia(
            codigo=AUSENCIA_ACTUALIZADA,
            cantidad=len(nuevas),
            ids=ids,
        )
    except Exception:
        _rollback(session)
        return ResultadoAusencia(codigo=AUSENCIA_ERROR_PERSISTENCIA)


def eliminar_ausencia_usuario(
    *,
    usuario_id,
    snapshot,
    secret_key,
    session=None,
):
    session = db.session if session is None else session
    try:
        filas, _, error = _filas_snapshot_bajo_lock(
            session,
            usuario_id=usuario_id,
            snapshot=snapshot,
            secret_key=secret_key,
        )
        if error is not None:
            return error
        if not _filas_editables_por_empleado(filas):
            return _resultado_y_liberar(session, AUSENCIA_SIN_PERMISOS)
        ids = tuple(item.id for item in filas)
        for ausencia in filas:
            session.delete(ausencia)
        session.commit()
        return ResultadoAusencia(
            codigo=AUSENCIA_ELIMINADA,
            cantidad=len(ids),
            ids=ids,
        )
    except Exception:
        _rollback(session)
        return ResultadoAusencia(codigo=AUSENCIA_ERROR_PERSISTENCIA)
