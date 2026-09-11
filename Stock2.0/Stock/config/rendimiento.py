"""Instrumentación ligera de rendimiento basada en ``perf_counter``."""

from __future__ import annotations

import logging
from collections import defaultdict
from contextlib import contextmanager
from time import perf_counter


class MetricasRendimiento:
    def __init__(self, contexto: str):
        self.contexto = contexto
        self._duraciones = defaultdict(float)
        self._conteos = defaultdict(int)

    @contextmanager
    def medir(self, fase: str):
        inicio = perf_counter()
        try:
            yield
        finally:
            self.registrar(fase, perf_counter() - inicio)

    def registrar(self, fase: str, segundos: float) -> None:
        self._duraciones[fase] += segundos
        self._conteos[fase] += 1

    def duracion(self, fase: str) -> float:
        return self._duraciones.get(fase, 0.0)

    def resumen(self) -> list[str]:
        return [
            f"- {fase}: {segundos:.2f} s"
            for fase, segundos in self._duraciones.items()
        ]

    def registrar_resumen(self, logger=None) -> None:
        logger = logger or logging.getLogger(__name__)
        logger.info("%s:\n%s", self.contexto, "\n".join(self.resumen()))


@contextmanager
def medir_fase(metricas: MetricasRendimiento | None, fase: str):
    """Mide una fase o actúa como contexto neutro si no hay métricas."""

    if metricas is None:
        yield
        return
    with metricas.medir(fase):
        yield


def commit_con_metricas(conexion, metricas: MetricasRendimiento | None = None) -> None:
    """Confirma una transacción midiendo el tiempo si hay métricas."""

    if metricas is None:
        conexion.commit()
        return
    with metricas.medir("Commits"):
        conexion.commit()
