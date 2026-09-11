"""Estado explícito de una ejecución de sincronización."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Iterable


class EstadoEjecucion(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


@dataclass
class ResultadoEjecucion:
    proveedores_correctos: set[int] = field(default_factory=set)
    proveedores_fallidos: set[int] = field(default_factory=set)
    advertencias: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    detalles_proveedores: dict[int, list[dict]] = field(default_factory=dict)
    metricas_proveedores: dict[int, dict] = field(default_factory=dict)
    metricas_globales: dict = field(default_factory=dict)
    fases_globales: dict[str, str] = field(default_factory=dict)
    intenciones_prestashop: list = field(default_factory=list, repr=False)
    plan_prestashop: dict = field(default_factory=dict)

    @property
    def estado(self) -> EstadoEjecucion:
        if self.proveedores_fallidos or self.errores:
            return EstadoEjecucion.FAILED
        if self.advertencias:
            return EstadoEjecucion.PARTIAL
        return EstadoEjecucion.SUCCESS

    def proveedor_correcto(self, id_proveedor: int) -> None:
        if id_proveedor not in self.proveedores_fallidos:
            self.proveedores_correctos.add(id_proveedor)

    def proveedor_fallido(self, id_proveedor: int, error: str) -> None:
        self.proveedores_correctos.discard(id_proveedor)
        self.proveedores_fallidos.add(id_proveedor)
        self.errores.append(f"Proveedor {id_proveedor}: {error}")

    def advertir(self, fase: str, error: str) -> None:
        self.advertencias.append(f"{fase}: {error}")

    def fallo_global(self, fase: str, error: str) -> None:
        self.errores.append(f"{fase}: {error}")


def _formatear_lista(valores: Iterable) -> str:
    valores = list(valores)
    return ", ".join(map(str, valores)) if valores else "ninguno"


def ocultar_secretos(texto: str, secretos: Iterable[str]) -> str:
    """Elimina valores sensibles conocidos de una salida operativa."""

    resultado = str(texto)
    valores = sorted(
        {str(valor) for valor in secretos if valor is not None and str(valor)},
        key=len,
        reverse=True,
    )
    for valor in valores:
        resultado = resultado.replace(valor, "[OCULTO]")
    resultado = re.sub(
        r"(?i)\b(?:https?|ftps?|sftp)://\S+",
        "[URL_OCULTA]",
        resultado,
    )
    resultado = re.sub(
        r"(?i)\b(password|passwd|pwd|token|secret)\s*[=:]\s*\S+",
        r"\1=[OCULTO]",
        resultado,
    )
    return resultado


def _sumar_detalles(resultado: ResultadoEjecucion) -> dict[str, object]:
    totales = {
        "variantes": 0,
        "coincidencias": 0,
        "conflictos": 0,
        "cambios_prestashop": 0,
        "activaciones": 0,
        "desactivaciones": 0,
        "reactivaciones": 0,
        "proveedores_con_conflictos": set(),
    }
    for id_proveedor, detalles in resultado.detalles_proveedores.items():
        variantes_persistidas = None
        for detalle in detalles or ():
            preparacion = detalle.get("preparacion_variantes", {})
            persistencia = detalle.get("persistencia", {})
            cruce = detalle.get("cruce", {})
            prestashop = detalle.get("prestashop", {})
            if (
                variantes_persistidas is None
                and "variantes_recibidas" in persistencia
            ):
                # La persistencia es única por proveedor, aunque un proveedor
                # tenga varias configuraciones y el detalle la referencie más
                # de una vez.
                variantes_persistidas = int(
                    persistencia.get("variantes_recibidas", 0) or 0
                )
            if "variantes_recibidas" not in persistencia:
                totales["variantes"] += int(
                    preparacion.get(
                        "filas_salida",
                        preparacion.get(
                            "filas",
                            persistencia.get("variantes_entrada", 0),
                        ),
                    )
                    or 0
                )
            coincidencias = cruce.get("coincidencias")
            if coincidencias is None:
                coincidencias = (
                    cruce.get("coincidencias_ean", 0)
                    + cruce.get("coincidencias_referencia", 0)
                    + cruce.get("resueltas_ean", 0)
                    + cruce.get("resueltas_referencia", 0)
                    + cruce.get("resueltas_historico", 0)
                )
            totales["coincidencias"] += int(coincidencias or 0)
            conflictos = int(cruce.get("conflictos", 0) or 0)
            totales["conflictos"] += conflictos
            if conflictos:
                totales["proveedores_con_conflictos"].add(id_proveedor)
            candidatos_reactivacion = prestashop.get(
                "candidatos_reactivacion", ()
            )
            candidatos_desactivacion = prestashop.get(
                "candidatos_desactivacion_simple", ()
            )
            candidatos_activacion = prestashop.get(
                "candidatos_activacion_producto", ()
            )
            cambios_preview = (
                len(candidatos_reactivacion)
                + len(candidatos_desactivacion)
                + len(candidatos_activacion)
            )
            totales["cambios_prestashop"] += int(
                prestashop.get("cambios_funcionales", cambios_preview) or 0
            )
            totales["activaciones"] += int(
                prestashop.get(
                    "productos_activados", len(candidatos_activacion)
                ) or 0
            )
            totales["desactivaciones"] += int(
                prestashop.get(
                    "productos_simples_desactivados",
                    len(candidatos_desactivacion),
                ) or 0
            )
            totales["reactivaciones"] += int(
                prestashop.get(
                    "atributos_reactivados", len(candidatos_reactivacion)
                ) or 0
            )
        if variantes_persistidas is not None:
            totales["variantes"] += variantes_persistidas
    if resultado.plan_prestashop:
        plan = resultado.plan_prestashop
        totales["cambios_prestashop"] = int(
            plan.get("cambios_funcionales", plan.get("cambios_finales", 0))
            or 0
        )
        totales["activaciones"] = int(plan.get("activaciones", 0) or 0)
        totales["desactivaciones"] = int(
            plan.get("desactivaciones", 0) or 0
        )
        totales["reactivaciones"] = int(
            plan.get("reactivaciones_id_shop_autorizadas", 0) or 0
        )
    elif resultado.estado is EstadoEjecucion.FAILED:
        # Sin plan global no hubo una decisión aplicable a PrestaShop. Los
        # candidatos parciales de proveedores no deben parecer cambios reales.
        totales["cambios_prestashop"] = 0
        totales["activaciones"] = 0
        totales["desactivaciones"] = 0
        totales["reactivaciones"] = 0
    return totales


def construir_notificacion(
    resultado: ResultadoEjecucion,
    *,
    duracion_segundos: float,
    logs: Iterable[str],
    secretos: Iterable[str] = (),
) -> tuple[str, str]:
    """Construye un asunto y cuerpo sin incluir datos de configuración."""

    estado = resultado.estado
    asuntos = {
        EstadoEjecucion.SUCCESS: "Proceso completado",
        EstadoEjecucion.PARTIAL: "Proceso parcial con advertencias",
        EstadoEjecucion.FAILED: "Proceso fallido",
    }
    lineas = [
        f"Estado: {estado.value}",
        f"Proveedores correctos: {_formatear_lista(sorted(resultado.proveedores_correctos))}",
        f"Proveedores fallidos: {_formatear_lista(sorted(resultado.proveedores_fallidos))}",
        f"Duración total: {duracion_segundos:.2f} segundos",
        f"Logs: {_formatear_lista(logs)}",
    ]
    totales = _sumar_detalles(resultado)
    lineas.extend(
        [
            f"Variantes procesadas: {totales['variantes']}",
            f"Coincidencias: {totales['coincidencias']}",
            f"Conflictos: {totales['conflictos']}",
            "Proveedores con conflictos: "
            + _formatear_lista(sorted(totales["proveedores_con_conflictos"])),
            f"Cambios PrestaShop: {totales['cambios_prestashop']}",
            f"Activaciones: {totales['activaciones']}",
            f"Desactivaciones: {totales['desactivaciones']}",
            f"Reactivaciones: {totales['reactivaciones']}",
            "Intenciones proveedor: "
            f"{resultado.plan_prestashop.get('intenciones_proveedor', 0)}",
            "Destinos únicos: "
            f"{resultado.plan_prestashop.get('destinos_unicos', 0)}",
            "Contradicciones: "
            f"{resultado.plan_prestashop.get('contradicciones', 0)}",
            "Combinaciones resueltas: "
            f"{resultado.plan_prestashop.get('combinaciones_resueltas', 0)}",
            "Padres resueltos: "
            f"{resultado.plan_prestashop.get('padres_resueltos', 0)}",
            "Packs detectados: "
            f"{resultado.plan_prestashop.get('packs_detectados', 0)}",
            "Packs excluidos: "
            f"{resultado.plan_prestashop.get('packs_excluidos', 0)}",
            "Acciones pack descartadas: "
            f"{resultado.plan_prestashop.get('acciones_pack_descartadas', 0)}",
            "PLAN DETALLADO: "
            f"{resultado.plan_prestashop.get('plan_detallado', 'no generado')}",
            "Activados: "
            f"{resultado.plan_prestashop.get('productos_activados_detallados', 0)}",
            "Desactivados: "
            f"{resultado.plan_prestashop.get('productos_desactivados_detallados', 0)}",
            "Pedido habilitado: "
            f"{resultado.plan_prestashop.get('pedidos_habilitados', 0)}",
            "Pedido deshabilitado: "
            f"{resultado.plan_prestashop.get('pedidos_deshabilitados', 0)}",
            "Combinaciones 99 → 1: "
            f"{resultado.plan_prestashop.get('combinaciones_99_a_1', 0)}",
            "Combinaciones 1 → 99: "
            f"{resultado.plan_prestashop.get('combinaciones_1_a_99', 0)}",
            "Conflictos descartados: "
            f"{resultado.plan_prestashop.get('conflictos_descartados', 0)}",
            "Visibilidad: "
            + resultado.fases_globales.get("visibilidad", "NO SOLICITADA"),
        ]
    )
    if resultado.advertencias:
        lineas.append("Advertencias:")
        lineas.extend(f"- {texto}" for texto in resultado.advertencias)
    if resultado.errores:
        lineas.append("Errores principales:")
        lineas.extend(f"- {texto}" for texto in resultado.errores)
    return asuntos[estado], ocultar_secretos("\n".join(lineas), secretos)


def construir_resumen_terminal(
    resultado: ResultadoEjecucion,
    *,
    total_proveedores: int,
    exit_code: int,
    cambios_aplicados: bool,
) -> str:
    """Resume el resultado funcional sin confundirlo con la notificación."""

    totales = _sumar_detalles(resultado)
    segundos = resultado.metricas_globales.get("segundos", {})
    duracion = float(segundos.get("Duración total", 0) or 0)
    fases_proveedor = {
        "Descarga": 0.0,
        "Parseo": 0.0,
        "Persistencia": 0.0,
        "Cruce": 0.0,
        "PrestaShop": 0.0,
    }
    for metricas in resultado.metricas_proveedores.values():
        duraciones = metricas.get("segundos", {})
        fases_proveedor["Descarga"] += float(
            duraciones.get("Descarga", 0) or 0
        )
        fases_proveedor["Parseo"] += float(
            duraciones.get("Procesamiento del fichero", 0) or 0
        )
        fases_proveedor["Persistencia"] += float(
            duraciones.get("Persistencia de variantes y resúmenes", 0) or 0
        )
        fases_proveedor["Cruce"] += float(
            duraciones.get("Cruces de DataFrames", 0) or 0
        )
        fases_proveedor["PrestaShop"] += float(
            duraciones.get("Actualización precisa de variantes", 0) or 0
        ) + float(
            duraciones.get("Informe previo sin escrituras PrestaShop", 0) or 0
        )
    visibilidad = float(segundos.get("Visibilidad", 0) or 0)
    fases_proveedor["PrestaShop"] += float(
        segundos.get("Resolución global PrestaShop", 0) or 0
    ) + float(
        segundos.get("Aplicación plan global PrestaShop", 0) or 0
    )
    plan = resultado.plan_prestashop
    return "\n".join(
        [
            f"RESULTADO: {resultado.estado.value}",
            "Proveedores: "
            f"{len(resultado.proveedores_correctos)}/{total_proveedores}",
            "Fallidos: "
            + _formatear_lista(sorted(resultado.proveedores_fallidos)),
            f"Variantes: {totales['variantes']}",
            f"Coincidencias: {totales['coincidencias']}",
            f"Conflictos: {totales['conflictos']}",
            f"Intenciones proveedor: {plan.get('intenciones_proveedor', 0)}",
            f"Destinos únicos: {plan.get('destinos_unicos', 0)}",
            f"Contradicciones: {plan.get('contradicciones', 0)}",
            "Combinaciones resueltas: "
            f"{plan.get('combinaciones_resueltas', 0)}",
            f"Padres resueltos: {plan.get('padres_resueltos', 0)}",
            f"Packs detectados: {plan.get('packs_detectados', 0)}",
            f"Packs excluidos: {plan.get('packs_excluidos', 0)}",
            "Acciones pack descartadas: "
            f"{plan.get('acciones_pack_descartadas', 0)}",
            f"PLAN DETALLADO: {plan.get('plan_detallado', 'no generado')}",
            f"Activados: {plan.get('productos_activados_detallados', 0)}",
            f"Desactivados: {plan.get('productos_desactivados_detallados', 0)}",
            f"Pedido habilitado: {plan.get('pedidos_habilitados', 0)}",
            f"Pedido deshabilitado: {plan.get('pedidos_deshabilitados', 0)}",
            f"Combinaciones 99 → 1: {plan.get('combinaciones_99_a_1', 0)}",
            f"Combinaciones 1 → 99: {plan.get('combinaciones_1_a_99', 0)}",
            f"Conflictos descartados: {plan.get('conflictos_descartados', 0)}",
            "Reactivaciones id_shop autorizadas: "
            f"{plan.get('reactivaciones_id_shop_autorizadas', 0)}",
            (
                "Cambios aplicados: "
                if cambios_aplicados
                else "Cambios propuestos: "
            )
            + f"{totales['cambios_prestashop']}",
            f"Descarga: {fases_proveedor['Descarga']:.2f} s",
            f"Parseo: {fases_proveedor['Parseo']:.2f} s",
            f"Persistencia: {fases_proveedor['Persistencia']:.2f} s",
            f"Cruce: {fases_proveedor['Cruce']:.2f} s",
            f"PrestaShop: {fases_proveedor['PrestaShop']:.2f} s",
            f"Visibilidad: {visibilidad:.2f} s",
            f"Duración: {duracion:.2f} s",
            f"EXIT CODE: {exit_code}",
        ]
    )
