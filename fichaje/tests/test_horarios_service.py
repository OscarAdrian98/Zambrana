from dataclasses import dataclass
from datetime import datetime, timedelta

from app.services.horarios import (
    formatear_duracion_corta,
    formatear_horas_minutos_texto,
    formatear_timedelta_hhmm,
    formatear_timedelta_hhmmss,
    formatear_total_horas,
    reconstruir_tramos,
)


@dataclass
class RegistroPrueba:
    tipo: str
    timestamp: datetime
    origen: str | None = "Tienda"
    eliminado: bool = False


BASE = datetime(2026, 1, 5, 8, 0)


def registro(tipo, horas=0, minutos=0, origen="Tienda", eliminado=False):
    return RegistroPrueba(
        tipo=tipo,
        timestamp=BASE + timedelta(hours=horas, minutes=minutos),
        origen=origen,
        eliminado=eliminado,
    )


def codigos(resultado):
    return [incidencia.codigo for incidencia in resultado.incidencias]


def test_sin_registros():
    resultado = reconstruir_tramos([])

    assert resultado.estado == "Sin fichaje"
    assert resultado.total_trabajado == timedelta()
    assert resultado.tramos == []
    assert resultado.entrada_abierta is None
    assert resultado.ultimo_registro is None
    assert resultado.incidencias == []


def test_entrada_abierta():
    entrada = registro("entrada")

    resultado = reconstruir_tramos([entrada])

    assert resultado.estado == "Dentro"
    assert resultado.entrada_abierta is entrada
    assert resultado.ultimo_registro is entrada
    assert resultado.total_trabajado == timedelta()
    assert codigos(resultado) == ["entrada_abierta"]


def test_bit_cero_de_mysql_no_se_interpreta_como_eliminado():
    entrada = registro("entrada", horas=8)
    entrada.eliminado = b"\x00"

    resultado = reconstruir_tramos([entrada])

    assert resultado.entrada_abierta is entrada


def test_bit_uno_de_mysql_se_interpreta_como_eliminado():
    entrada = registro("entrada", horas=8)
    entrada.eliminado = b"\x01"

    resultado = reconstruir_tramos([entrada])

    assert resultado.registros_activos == []


def test_entrada_y_salida():
    entrada = registro("entrada")
    salida = registro("salida", horas=1, minutos=30)

    resultado = reconstruir_tramos([entrada, salida])

    assert resultado.estado == "Fuera"
    assert resultado.total_trabajado == timedelta(hours=1, minutes=30)
    assert len(resultado.tramos) == 1
    assert resultado.tramos[0].entrada is entrada
    assert resultado.tramos[0].salida is salida
    assert resultado.incidencias == []


def test_dos_tramos():
    registros = [
        registro("entrada"),
        registro("salida", horas=1),
        registro("entrada", horas=2),
        registro("salida", horas=4),
    ]

    resultado = reconstruir_tramos(registros)

    assert len(resultado.tramos) == 2
    assert resultado.total_trabajado == timedelta(hours=3)


def test_tres_o_mas_tramos():
    registros = [
        registro("entrada"),
        registro("salida", horas=1),
        registro("entrada", horas=2),
        registro("salida", horas=3),
        registro("entrada", horas=4),
        registro("salida", horas=6),
        registro("entrada", horas=7),
        registro("salida", horas=8),
    ]

    resultado = reconstruir_tramos(registros)

    assert len(resultado.tramos) == 4
    assert resultado.total_trabajado == timedelta(hours=5)


def test_registros_desordenados_por_fecha():
    entrada = registro("entrada")
    salida = registro("salida", horas=2)

    resultado = reconstruir_tramos([salida, entrada])

    assert resultado.registros_activos == [entrada, salida]
    assert resultado.total_trabajado == timedelta(hours=2)
    assert resultado.estado == "Fuera"


def test_registro_eliminado_intercalado():
    eliminado = registro("salida", minutos=30, eliminado=True)
    entrada = registro("entrada")
    salida = registro("salida", horas=2)

    resultado = reconstruir_tramos([entrada, eliminado, salida])

    assert resultado.registros_activos == [entrada, salida]
    assert eliminado not in resultado.registros_activos
    assert resultado.total_trabajado == timedelta(hours=2)


def test_doble_entrada_conserva_la_primera():
    primera = registro("entrada")
    segunda = registro("entrada", horas=1)
    salida = registro("salida", horas=2)

    resultado = reconstruir_tramos([primera, segunda, salida])

    assert "doble_entrada" in codigos(resultado)
    assert len(resultado.tramos) == 1
    assert resultado.tramos[0].entrada is primera
    assert resultado.total_trabajado == timedelta(hours=2)
    assert resultado.estado == "Fuera"


def test_doble_salida():
    registros = [
        registro("entrada"),
        registro("salida", horas=1),
        registro("salida", horas=2),
    ]

    resultado = reconstruir_tramos(registros)

    assert "doble_salida" in codigos(resultado)
    assert resultado.total_trabajado == timedelta(hours=1)
    assert resultado.estado == "Fuera"


def test_salida_inicial_sin_entrada():
    salida = registro("salida")

    resultado = reconstruir_tramos([salida])

    assert codigos(resultado) == ["salida_sin_entrada"]
    assert resultado.total_trabajado == timedelta()
    assert resultado.estado == "Fuera"


def test_entrada_final_sin_salida():
    entrada_final = registro("entrada", horas=2)
    registros = [
        registro("entrada"),
        registro("salida", horas=1),
        entrada_final,
    ]

    resultado = reconstruir_tramos(registros)

    assert len(resultado.tramos) == 1
    assert resultado.total_trabajado == timedelta(hours=1)
    assert resultado.entrada_abierta is entrada_final
    assert resultado.estado == "Dentro"
    assert "entrada_abierta" in codigos(resultado)


def test_salida_anterior_a_la_entrada_no_inventa_horas():
    entrada = registro("entrada", horas=2)
    salida_anterior = registro("salida", horas=1)

    resultado = reconstruir_tramos([entrada, salida_anterior])

    assert resultado.total_trabajado == timedelta()
    assert resultado.tramos == []
    assert resultado.entrada_abierta is entrada
    assert codigos(resultado) == ["salida_sin_entrada", "entrada_abierta"]


def test_duracion_no_positiva_se_registra_como_incidencia():
    entrada = registro("entrada")
    salida = registro("salida")

    resultado = reconstruir_tramos([entrada, salida])

    assert resultado.total_trabajado == timedelta()
    assert resultado.tramos == []
    assert resultado.entrada_abierta is entrada
    assert "duracion_no_positiva" in codigos(resultado)


def test_origen_se_conserva_en_el_tramo():
    entrada = registro("entrada", origen="Auto")
    salida = registro("salida", horas=1, origen="Auto")

    resultado = reconstruir_tramos([entrada, salida])
    tramo = resultado.tramos[0]

    assert tramo.origen_entrada == "Auto"
    assert tramo.origen_salida == "Auto"


def test_total_superior_a_24_horas_y_formatos():
    entrada = registro("entrada")
    salida = RegistroPrueba(
        tipo="salida",
        timestamp=BASE + timedelta(hours=27, minutes=15, seconds=9),
    )

    resultado = reconstruir_tramos([entrada, salida])

    assert resultado.total_trabajado == timedelta(hours=27, minutes=15, seconds=9)
    assert formatear_timedelta_hhmm(resultado.total_trabajado) == "27:15"
    assert formatear_timedelta_hhmmss(resultado.total_trabajado) == "27:15:09"
    assert formatear_total_horas(resultado.total_trabajado) == "27h 15m 9s"
    assert formatear_duracion_corta(resultado.total_trabajado) == "27:15"
    assert (
        formatear_horas_minutos_texto(resultado.total_trabajado) == "27 h 15 m"
    )


def test_tipo_desconocido():
    desconocido = registro("pausa")

    resultado = reconstruir_tramos([desconocido])

    assert resultado.estado == "Sin fichaje"
    assert resultado.ultimo_registro is desconocido
    assert resultado.registros_activos == [desconocido]
    assert codigos(resultado) == ["tipo_desconocido"]
