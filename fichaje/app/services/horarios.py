from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any


@dataclass(frozen=True)
class TramoHorario:
    entrada: Any
    salida: Any
    duracion: timedelta
    origen_entrada: str | None
    origen_salida: str | None


@dataclass(frozen=True)
class IncidenciaHorario:
    codigo: str
    registro: Any
    relacionado: Any | None = None


@dataclass
class ReconstruccionHoraria:
    tramos: list[TramoHorario] = field(default_factory=list)
    entrada_abierta: Any | None = None
    total_trabajado: timedelta = field(default_factory=timedelta)
    ultimo_registro: Any | None = None
    ultima_entrada: Any | None = None
    ultima_salida: Any | None = None
    estado: str = "Sin fichaje"
    incidencias: list[IncidenciaHorario] = field(default_factory=list)
    registros_activos: list[Any] = field(default_factory=list)


def es_valor_booleano_verdadero(valor) -> bool:
    """Normaliza bool, BIT(1) de MySQL y valores escalares equivalentes."""
    if isinstance(valor, (bytes, bytearray, memoryview)):
        contenido = bytes(valor)
        return int.from_bytes(contenido, byteorder="big") != 0
    return bool(valor)


def esta_eliminado(registro) -> bool:
    return es_valor_booleano_verdadero(
        getattr(registro, "eliminado", False)
    )


def reconstruir_tramos(registros) -> ReconstruccionHoraria:
    """Interpreta registros sin modificarlos ni acceder a la base de datos.

    La política es deliberadamente conservadora: la primera entrada permanece
    abierta ante entradas consecutivas; una salida solo la cierra cuando es
    posterior; y una salida aislada nunca crea ni suma un tramo ficticio. Las
    anomalías se conservan como incidencias para que la capa de presentación
    decida cómo comunicarlas.
    """
    activos = sorted(
        (registro for registro in registros if not esta_eliminado(registro)),
        key=lambda registro: registro.timestamp,
    )
    resultado = ReconstruccionHoraria(
        ultimo_registro=activos[-1] if activos else None,
        registros_activos=activos,
    )

    entrada_abierta = None
    ultimo_tipo_conocido = None
    hay_registro_conocido = False

    for registro in activos:
        tipo = str(getattr(registro, "tipo", "")).strip().lower()

        if tipo == "entrada":
            hay_registro_conocido = True
            resultado.ultima_entrada = registro

            if entrada_abierta is None:
                entrada_abierta = registro
            else:
                resultado.incidencias.append(
                    IncidenciaHorario(
                        codigo="doble_entrada",
                        registro=registro,
                        relacionado=entrada_abierta,
                    )
                )

            ultimo_tipo_conocido = "entrada"
            continue

        if tipo == "salida":
            hay_registro_conocido = True
            resultado.ultima_salida = registro

            if entrada_abierta is None:
                codigo = (
                    "doble_salida"
                    if ultimo_tipo_conocido == "salida"
                    else "salida_sin_entrada"
                )
                resultado.incidencias.append(
                    IncidenciaHorario(codigo=codigo, registro=registro)
                )
            else:
                duracion = registro.timestamp - entrada_abierta.timestamp
                if duracion.total_seconds() > 0:
                    resultado.tramos.append(
                        TramoHorario(
                            entrada=entrada_abierta,
                            salida=registro,
                            duracion=duracion,
                            origen_entrada=getattr(entrada_abierta, "origen", None),
                            origen_salida=getattr(registro, "origen", None),
                        )
                    )
                    resultado.total_trabajado += duracion
                    entrada_abierta = None
                else:
                    resultado.incidencias.append(
                        IncidenciaHorario(
                            codigo="duracion_no_positiva",
                            registro=registro,
                            relacionado=entrada_abierta,
                        )
                    )

            ultimo_tipo_conocido = "salida"
            continue

        resultado.incidencias.append(
            IncidenciaHorario(codigo="tipo_desconocido", registro=registro)
        )

    resultado.entrada_abierta = entrada_abierta
    if entrada_abierta is not None:
        resultado.estado = "Dentro"
        resultado.incidencias.append(
            IncidenciaHorario(codigo="entrada_abierta", registro=entrada_abierta)
        )
    elif hay_registro_conocido:
        resultado.estado = "Fuera"

    return resultado


def _componentes_duracion(duracion: timedelta) -> tuple[int, int, int]:
    total_segundos = max(0, int(duracion.total_seconds()))
    horas = total_segundos // 3600
    minutos = (total_segundos % 3600) // 60
    segundos = total_segundos % 60
    return horas, minutos, segundos


def formatear_timedelta_hhmm(duracion: timedelta) -> str:
    horas, minutos, _ = _componentes_duracion(duracion)
    return f"{horas:02d}:{minutos:02d}"


def formatear_timedelta_hhmmss(duracion: timedelta) -> str:
    horas, minutos, segundos = _componentes_duracion(duracion)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"


def formatear_total_horas(duracion: timedelta) -> str:
    horas, minutos, segundos = _componentes_duracion(duracion)
    return f"{horas}h {minutos}m {segundos}s"


def formatear_duracion_corta(duracion: timedelta) -> str:
    return formatear_timedelta_hhmm(duracion)


def formatear_horas_minutos_texto(duracion: timedelta) -> str:
    horas, minutos, _ = _componentes_duracion(duracion)
    return f"{horas:02d} h {minutos:02d} m"
