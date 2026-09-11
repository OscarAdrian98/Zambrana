from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time
import re
from typing import Any, Iterable

from itsdangerous import BadSignature, URLSafeSerializer

from app.services.horarios import ReconstruccionHoraria, esta_eliminado


ORIGENES_ADMIN_PERMITIDOS = ("Tienda", "Remoto", "Auto")
MAX_TRAMOS_POR_FICHAJE = 50
_PATRON_HORA = re.compile(r"^[0-9]{2}:[0-9]{2}$")
_PATRON_TRAMO = re.compile(
    r"^tramos\[([A-Za-z0-9_-]+)\]"
    r"\[(entrada_id|salida_id|entrada|salida|origen|eliminar)\]$"
)
_PATRON_IRREGULAR = re.compile(
    r"^irregulares\[([A-Za-z0-9_-]+)\]\[(registro_id|eliminar)\]$"
)
_SAL_SNAPSHOT = "edicion-fichaje-admin-v1"
_SAL_SNAPSHOT_BORRADO = "borrado-fichaje-admin-v1"


class ErrorEdicionFichaje(ValueError):
    pass


class ErrorSnapshotEdicionFichaje(ErrorEdicionFichaje):
    pass


class ErrorRegistroEdicionFichaje(ErrorEdicionFichaje):
    pass


class ErrorSnapshotBorradoFichaje(ValueError):
    pass


@dataclass(frozen=True)
class TramoEditable:
    clave: str
    entrada_id: int
    salida_id: int | None
    entrada: str
    salida: str
    origen: str
    origen_salida: str | None
    incompleto: bool


@dataclass(frozen=True)
class IncidenciaEditable:
    clave: str
    registro_id: int
    codigo: str
    mensaje: str


@dataclass(frozen=True)
class PreparacionEdicion:
    tramos: tuple[TramoEditable, ...]
    avisos: tuple[str, ...]
    irregulares: tuple[IncidenciaEditable, ...]


@dataclass(frozen=True)
class TramoSolicitado:
    clave: str
    entrada_id: int | None
    salida_id: int | None
    entrada: time
    salida: time | None
    origen: str
    eliminar: bool


@dataclass(frozen=True)
class SolicitudEdicion:
    tramos: tuple[TramoSolicitado, ...]
    irregulares_a_eliminar: frozenset[int]


def _descripcion_incidencia(incidencia: Any) -> str:
    hora = incidencia.registro.timestamp.strftime("%H:%M")
    descripciones = {
        "doble_entrada": f"Doble entrada detectada a las {hora}.",
        "doble_salida": f"Doble salida detectada a las {hora}.",
        "salida_sin_entrada": f"Salida sin entrada detectada a las {hora}.",
        "duracion_no_positiva": f"Duración no positiva detectada a las {hora}.",
        "entrada_abierta": f"Entrada abierta desde las {hora}.",
        "tipo_desconocido": f"Tipo de registro desconocido a las {hora}.",
    }
    return descripciones.get(
        incidencia.codigo,
        f"Incidencia horaria detectada a las {hora}.",
    )


def preparar_edicion(resultado: ReconstruccionHoraria) -> PreparacionEdicion:
    tramos = [
        TramoEditable(
            clave=f"existente_{tramo.entrada.id}_{tramo.salida.id}",
            entrada_id=tramo.entrada.id,
            salida_id=tramo.salida.id,
            entrada=tramo.entrada.timestamp.strftime("%H:%M"),
            salida=tramo.salida.timestamp.strftime("%H:%M"),
            origen=tramo.origen_entrada or "Tienda",
            origen_salida=tramo.origen_salida,
            incompleto=False,
        )
        for tramo in resultado.tramos
    ]

    if resultado.entrada_abierta is not None:
        entrada = resultado.entrada_abierta
        tramos.append(
            TramoEditable(
                clave=f"existente_{entrada.id}_abierto",
                entrada_id=entrada.id,
                salida_id=None,
                entrada=entrada.timestamp.strftime("%H:%M"),
                salida="",
                origen=getattr(entrada, "origen", None) or "Tienda",
                origen_salida=None,
                incompleto=True,
            )
        )

    irregulares = []
    ids_irregulares = set()
    for incidencia in resultado.incidencias:
        if incidencia.codigo == "entrada_abierta":
            continue
        registro = incidencia.registro
        registro_id = getattr(registro, "id", None)
        if registro_id is None or registro_id in ids_irregulares:
            continue
        ids_irregulares.add(registro_id)
        irregulares.append(
            IncidenciaEditable(
                clave=f"irregular_{registro_id}",
                registro_id=registro_id,
                codigo=incidencia.codigo,
                mensaje=_descripcion_incidencia(incidencia),
            )
        )

    return PreparacionEdicion(
        tramos=tuple(tramos),
        avisos=tuple(
            _descripcion_incidencia(incidencia)
            for incidencia in resultado.incidencias
        ),
        irregulares=tuple(irregulares),
    )


def _datos_snapshot(fichaje_id: int, registros: Iterable[Any]) -> dict[str, Any]:
    activos = sorted(
        (registro for registro in registros if not esta_eliminado(registro)),
        key=lambda registro: (registro.timestamp, registro.id),
    )
    return {
        "fichaje_id": fichaje_id,
        "registros": [
            [
                registro.id,
                registro.tipo,
                registro.timestamp.isoformat(timespec="microseconds"),
                registro.origen,
                esta_eliminado(registro),
            ]
            for registro in activos
        ],
    }


def crear_snapshot_firmado(
    fichaje_id: int,
    registros: Iterable[Any],
    secret_key: str,
) -> str:
    serializer = URLSafeSerializer(secret_key, salt=_SAL_SNAPSHOT)
    return serializer.dumps(_datos_snapshot(fichaje_id, registros))


def validar_snapshot_firmado(
    token: str,
    fichaje_id: int,
    registros: Iterable[Any],
    secret_key: str,
) -> None:
    if not token:
        raise ErrorSnapshotEdicionFichaje("Falta la huella de edición.")

    serializer = URLSafeSerializer(secret_key, salt=_SAL_SNAPSHOT)
    try:
        recibido = serializer.loads(token)
    except BadSignature as exc:
        raise ErrorSnapshotEdicionFichaje(
            "La huella de edición no es válida."
        ) from exc

    actual = _datos_snapshot(fichaje_id, registros)
    if recibido != actual:
        raise ErrorSnapshotEdicionFichaje(
            "El fichaje fue modificado por otra operación. Recarga la página."
        )


def _datos_snapshot_borrado(
    fichaje: Any,
    registros: Iterable[Any],
) -> dict[str, Any]:
    return {
        "fichaje_id": fichaje.id,
        "usuario_id": fichaje.usuario_id,
        "fecha": fichaje.fecha.isoformat(),
        "eliminado": bool(fichaje.eliminado),
        "estado": _datos_snapshot(fichaje.id, registros)["registros"],
    }


def crear_snapshot_borrado_firmado(
    fichaje: Any,
    registros: Iterable[Any],
    secret_key: str,
) -> str:
    serializer = URLSafeSerializer(secret_key, salt=_SAL_SNAPSHOT_BORRADO)
    return serializer.dumps(_datos_snapshot_borrado(fichaje, registros))


def validar_snapshot_borrado_firmado(
    token: str,
    fichaje: Any,
    registros: Iterable[Any],
    secret_key: str,
) -> None:
    if not token:
        raise ErrorSnapshotBorradoFichaje("Falta la huella de borrado.")

    serializer = URLSafeSerializer(secret_key, salt=_SAL_SNAPSHOT_BORRADO)
    try:
        recibido = serializer.loads(token)
    except BadSignature as exc:
        raise ErrorSnapshotBorradoFichaje(
            "La huella de borrado no es válida."
        ) from exc

    if recibido != _datos_snapshot_borrado(fichaje, registros):
        raise ErrorSnapshotBorradoFichaje(
            "El fichaje fue modificado por otra operación. Recarga la página."
        )


def _agrupar_campos(
    pares: Iterable[tuple[str, str]],
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    tramos: dict[str, dict[str, str]] = {}
    irregulares: dict[str, dict[str, str]] = {}

    for nombre, valor in pares:
        if nombre == "snapshot":
            continue

        coincidencia = _PATRON_TRAMO.match(nombre)
        destino = tramos
        if coincidencia is None:
            coincidencia = _PATRON_IRREGULAR.match(nombre)
            destino = irregulares

        if coincidencia is None:
            if nombre.startswith(("tramos[", "irregulares[")):
                raise ErrorEdicionFichaje("El formulario de edición está mal formado.")
            continue

        clave, campo = coincidencia.groups()
        grupo = destino.setdefault(clave, {})
        if campo in grupo:
            raise ErrorEdicionFichaje("El formulario contiene campos duplicados.")
        grupo[campo] = valor

    return tramos, irregulares


def _parsear_id(valor: str, nombre: str) -> int | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    if not valor.isascii() or not valor.isdecimal():
        raise ErrorRegistroEdicionFichaje(
            f"El identificador de {nombre} no es válido."
        )
    identificador = int(valor)
    if identificador <= 0:
        raise ErrorRegistroEdicionFichaje(
            f"El identificador de {nombre} no es válido."
        )
    return identificador


def _parsear_hora(valor: str, nombre: str) -> time | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    if not _PATRON_HORA.fullmatch(valor):
        raise ErrorEdicionFichaje(f"La hora de {nombre} no es válida.")
    try:
        return datetime.strptime(valor, "%H:%M").time()
    except ValueError as exc:
        raise ErrorEdicionFichaje(f"La hora de {nombre} no es válida.") from exc


def _validar_secuencia(tramos: list[TramoSolicitado]) -> None:
    activos = [tramo for tramo in tramos if not tramo.eliminar]
    abiertos = [tramo for tramo in activos if tramo.salida is None]
    if len(abiertos) > 1:
        raise ErrorEdicionFichaje("Solo puede existir una entrada abierta.")

    cerrados = [tramo for tramo in activos if tramo.salida is not None]
    intervalos = [(tramo.entrada, tramo.salida) for tramo in cerrados]
    if len(intervalos) != len(set(intervalos)):
        raise ErrorEdicionFichaje("No se permiten tramos duplicados.")

    cerrados.sort(key=lambda tramo: tramo.entrada)
    for anterior, siguiente in zip(cerrados, cerrados[1:]):
        if siguiente.entrada < anterior.salida:
            raise ErrorEdicionFichaje("Los tramos no pueden solaparse.")

    if abiertos and cerrados:
        ultima_salida = max(tramo.salida for tramo in cerrados)
        if abiertos[0].entrada < ultima_salida:
            raise ErrorEdicionFichaje(
                "La entrada abierta debe ser posterior a los tramos cerrados."
            )


def parsear_y_validar_formulario(
    pares: Iterable[tuple[str, str]],
    preparacion: PreparacionEdicion,
    registros_activos: Iterable[Any],
) -> SolicitudEdicion:
    grupos_tramos, grupos_irregulares = _agrupar_campos(pares)
    if len(grupos_tramos) > MAX_TRAMOS_POR_FICHAJE:
        raise ErrorEdicionFichaje("Se ha superado el límite de tramos permitido.")

    registros = {registro.id: registro for registro in registros_activos}
    pares_esperados = Counter(
        (tramo.entrada_id, tramo.salida_id) for tramo in preparacion.tramos
    )
    pares_recibidos: Counter[tuple[int, int | None]] = Counter()
    ids_usados = set()
    tramos_solicitados = []

    campos_obligatorios = {
        "entrada_id",
        "salida_id",
        "entrada",
        "salida",
        "origen",
        "eliminar",
    }
    for clave, campos in grupos_tramos.items():
        if set(campos) != campos_obligatorios:
            raise ErrorEdicionFichaje("El formulario de edición está incompleto.")

        entrada_id = _parsear_id(campos["entrada_id"], "entrada")
        salida_id = _parsear_id(campos["salida_id"], "salida")
        entrada = _parsear_hora(campos["entrada"], "entrada")
        salida = _parsear_hora(campos["salida"], "salida")
        eliminar = campos["eliminar"] == "1"
        if campos["eliminar"] not in {"0", "1"}:
            raise ErrorEdicionFichaje("La acción solicitada no es válida.")

        if entrada_id is None and salida_id is None and entrada is None and salida is None:
            continue
        if entrada is None:
            raise ErrorEdicionFichaje("No se permite una salida sin entrada.")
        if salida is not None and entrada >= salida:
            raise ErrorEdicionFichaje(
                "La entrada debe ser anterior a la salida y no puede cruzar medianoche."
            )

        origen = (campos["origen"] or "").strip()
        if origen not in ORIGENES_ADMIN_PERMITIDOS:
            raise ErrorEdicionFichaje("El origen seleccionado no es válido.")

        if entrada_id is not None or salida_id is not None:
            par = (entrada_id, salida_id)
            if par not in pares_esperados:
                raise ErrorRegistroEdicionFichaje(
                    "Los registros enviados no corresponden al fichaje editable."
                )
            pares_recibidos[par] += 1

        for identificador, tipo_esperado in (
            (entrada_id, "entrada"),
            (salida_id, "salida"),
        ):
            if identificador is None:
                continue
            if identificador in ids_usados:
                raise ErrorRegistroEdicionFichaje(
                    "Un registro no puede utilizarse en más de un tramo."
                )
            registro = registros.get(identificador)
            if registro is None or registro.tipo != tipo_esperado:
                raise ErrorRegistroEdicionFichaje(
                    "Los registros enviados no corresponden al fichaje editable."
                )
            ids_usados.add(identificador)

        tramos_solicitados.append(
            TramoSolicitado(
                clave=clave,
                entrada_id=entrada_id,
                salida_id=salida_id,
                entrada=entrada,
                salida=salida,
                origen=origen,
                eliminar=eliminar,
            )
        )

    if pares_recibidos != pares_esperados:
        raise ErrorEdicionFichaje(
            "Faltan tramos existentes en el formulario. Recarga la página."
        )

    ids_irregulares_esperados = {
        incidencia.registro_id for incidencia in preparacion.irregulares
    }
    ids_irregulares_recibidos = set()
    irregulares_a_eliminar = set()
    for campos in grupos_irregulares.values():
        if set(campos) - {"registro_id", "eliminar"} or "registro_id" not in campos:
            raise ErrorEdicionFichaje("El formulario de incidencias está mal formado.")
        registro_id = _parsear_id(campos["registro_id"], "incidencia")
        if registro_id is None or registro_id in ids_irregulares_recibidos:
            raise ErrorRegistroEdicionFichaje(
                "La referencia de incidencia no es válida."
            )
        if registro_id not in ids_irregulares_esperados:
            raise ErrorRegistroEdicionFichaje(
                "La referencia de incidencia no es válida."
            )
        if registro_id in ids_usados or registro_id not in registros:
            raise ErrorRegistroEdicionFichaje(
                "La referencia de incidencia no es válida."
            )
        eliminar = campos.get("eliminar", "0")
        if eliminar not in {"0", "1"}:
            raise ErrorEdicionFichaje("La acción de incidencia no es válida.")
        if eliminar == "1":
            irregulares_a_eliminar.add(registro_id)
        ids_irregulares_recibidos.add(registro_id)

    if ids_irregulares_recibidos != ids_irregulares_esperados:
        raise ErrorEdicionFichaje(
            "Faltan incidencias existentes en el formulario. Recarga la página."
        )

    _validar_secuencia(tramos_solicitados)
    return SolicitudEdicion(
        tramos=tuple(
            sorted(
                tramos_solicitados,
                key=lambda tramo: (tramo.entrada, tramo.salida or time.max),
            )
        ),
        irregulares_a_eliminar=frozenset(irregulares_a_eliminar),
    )


def combinar_fecha_hora(fecha: date, hora: time) -> datetime:
    return datetime.combine(fecha, hora)


def texto_tramo(entrada: time, salida: time | None) -> str:
    final = salida.strftime("%H:%M") if salida else "OPEN"
    texto = f"{entrada.strftime('%H:%M')}-{final}"
    if len(texto) > 20:
        raise ValueError("La representación de auditoría supera 20 caracteres.")
    return texto
