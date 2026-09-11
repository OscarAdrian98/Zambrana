"""Escritura transaccional de los sábados asignados de un usuario."""

from dataclasses import dataclass
from datetime import date, timedelta
import re

from sqlalchemy import delete, select

from app.models import SabadoAsignado, Usuario
from app.services.ausencias import fecha_hoy_madrid


SABADOS_GUARDADOS = "SABADOS_GUARDADOS"
SABADOS_FECHAS_INVALIDAS = "SABADOS_FECHAS_INVALIDAS"
SABADOS_USUARIO_INEXISTENTE = "SABADOS_USUARIO_INEXISTENTE"
SABADOS_ERROR_PERSISTENCIA = "SABADOS_ERROR_PERSISTENCIA"

_PATRON_FECHA = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


@dataclass(frozen=True)
class ResultadoSabadosAsignados:
    codigo: str
    usuario_id: int | None
    fechas: tuple[date, ...] = ()


def sabados_del_mes(referencia: date) -> tuple[date, ...]:
    primer_dia = referencia.replace(day=1)
    candidato = primer_dia
    resultado = []
    while candidato.month == primer_dia.month:
        if candidato.weekday() == 5:
            resultado.append(candidato)
        candidato += timedelta(days=1)
    return tuple(resultado)


def _rollback(session) -> None:
    try:
        session.rollback()
    except Exception:
        pass


def _identificador_positivo(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


def _parsear_fechas(fechas_solicitadas, permitidas):
    if not isinstance(fechas_solicitadas, (list, tuple)):
        raise ValueError("colección de fechas inválida")
    if len(fechas_solicitadas) > len(permitidas):
        raise ValueError("demasiadas fechas")

    fechas = []
    for valor in fechas_solicitadas:
        if not isinstance(valor, str) or not _PATRON_FECHA.fullmatch(valor):
            raise ValueError("fecha inválida")
        try:
            fechas.append(date.fromisoformat(valor))
        except ValueError as exc:
            raise ValueError("fecha inválida") from exc

    if len(set(fechas)) != len(fechas):
        raise ValueError("fecha duplicada")
    if any(fecha not in permitidas for fecha in fechas):
        raise ValueError("fecha no permitida")
    return tuple(sorted(fechas))


def guardar_sabados_asignados(
    session,
    *,
    usuario_id,
    fechas_solicitadas,
    fecha_referencia=None,
) -> ResultadoSabadosAsignados:
    """Reemplaza los sábados del mes mediante un único commit.

    La sesión recibida debe estar limpia. En MySQL/MariaDB se bloquea primero
    la fila estable de ``Usuario`` para serializar reemplazos concurrentes del
    mismo usuario. Las fechas históricas de otros meses permanecen intactas.
    """

    def omitir(codigo):
        _rollback(session)
        return ResultadoSabadosAsignados(
            codigo=codigo,
            usuario_id=usuario_id if _identificador_positivo(usuario_id) else None,
        )

    if not _identificador_positivo(usuario_id):
        return omitir(SABADOS_USUARIO_INEXISTENTE)

    referencia = fecha_referencia or fecha_hoy_madrid()
    if not isinstance(referencia, date):
        return omitir(SABADOS_FECHAS_INVALIDAS)

    permitidas = sabados_del_mes(referencia)
    try:
        fechas = _parsear_fechas(fechas_solicitadas, set(permitidas))
    except (TypeError, ValueError):
        return omitir(SABADOS_FECHAS_INVALIDAS)

    inicio_mes = referencia.replace(day=1)
    fin_mes = (inicio_mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    try:
        statement = select(Usuario).where(Usuario.id == usuario_id)
        if session.get_bind().dialect.name in {"mysql", "mariadb"}:
            statement = statement.with_for_update()
        usuario = session.execute(statement).scalar_one_or_none()
        if usuario is None:
            return omitir(SABADOS_USUARIO_INEXISTENTE)

        session.execute(
            delete(SabadoAsignado).where(
                SabadoAsignado.usuario_id == usuario_id,
                SabadoAsignado.fecha >= inicio_mes,
                SabadoAsignado.fecha <= fin_mes,
            )
        )
        session.add_all(
            SabadoAsignado(usuario_id=usuario_id, fecha=fecha)
            for fecha in fechas
        )
        session.commit()
        return ResultadoSabadosAsignados(
            codigo=SABADOS_GUARDADOS,
            usuario_id=usuario_id,
            fechas=fechas,
        )
    except Exception:
        _rollback(session)
        return ResultadoSabadosAsignados(
            codigo=SABADOS_ERROR_PERSISTENCIA,
            usuario_id=usuario_id,
        )
