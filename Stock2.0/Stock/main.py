import logging
import os
import time
from pathlib import Path

import pandas as pd

from config.bd import (
    BASE_PRESTASHOP_ACTIVA,
    BASE_PRESTASHOP_LOCAL,
    BASE_PRESTASHOP_PRUEBAS_REMOTA,
    BASE_PROVEEDORES_ACTIVA,
    BASE_PROVEEDORES_LOCAL,
    BASE_PROVEEDORES_OPERATIVA,
    TIPO_PRESTASHOP,
    TIPO_PROVEEDORES,
    cerrar_conexion,
    conectar_prestashop,
    conectar_proveedores,
    es_entorno_operativo,
    es_entorno_prueba_proveedores_operativos,
    es_entorno_validacion_remota,
    prestashop_config,
    proveedores_config,
    validar_entorno_configurado,
)
from config.configuracion_proveedor import (
    obtener_configuraciones_proveedor,
    obtener_marcas_permitidas_configuracion,
    obtener_resolucion_marca_configuracion,
)
from config.email import enviar_correo, nombre_visible_informe
from config.informe_cambios import persistir_informe_cambios
from config.logging import logger_funciones_especificas, rutas_logs
from config.retencion import limpiar_archivos_antiguos
from config.fuentes_validacion import (
    AlmacenFuentesValidacion,
    MODO_CAPTURA,
    calcular_identidad_configuracion,
)
from config.lote_validacion import PROVEEDORES_OPERATIVOS_VALIDACION
from config.rendimiento import MetricasRendimiento
from config.operativa import (
    BloqueoEjecucionOperativa,
    validar_preflight_operativo,
    validar_preflight_prueba_proveedores_operativos,
)
from config.resultado import (
    EstadoEjecucion,
    ResultadoEjecucion,
    construir_notificacion,
    ocultar_secretos,
)
from config.trazabilidad import (
    nuevo_execution_id,
    persistir_plan_detallado,
    persistir_resultado_ejecucion,
    registrar_acciones_humanas,
)
from etiquetas.activar_desactivar import (
    detectar_productos_obsoletos_para_desactivar,
)
from etiquetas.plan_global import construir_plan_global, aplicar_plan_global
from procesamiento.procesar_contenido import (
    descargar_y_procesar_archivo,
    procesar_archivo_excel,
)
from procesamiento.reglas import (
    calcular_disponibilidad_series,
    normalizar_serie_identificadores,
)
from procesamiento.marcas_multiples import resolver_marcas_multiples
from procesamiento.tablas_auxiliares import (
    añadir_referencias_colgadas,
    comparar_tablas_auxiliares,
    corregir_visibilidad_productos_ocultos,
    crear_tabla_aux_prestashop,
    crear_tabla_aux_proveedor,
    detectar_referencias_huerfanas_para_desactivar,
)
from procesamiento.variantes import (
    persistir_variantes_y_resumen,
    preparar_variantes_o_fallar,
)




def _extraer_configuracion(configuracion, id_proveedor, numero):
    if len(configuracion) < 15:
        raise ValueError(
            f"Configuración {numero} del proveedor {id_proveedor} incompleta: "
            "se esperaban 15 campos"
        )
    excel_config = {
        "col_referencia_configuracion": configuracion[6],
        "col_referencia_alternativa_configuracion": (
            configuracion[16] if len(configuracion) > 16 else None
        ),
        "col_ean_configuracion": configuracion[13],
        "col_fecha_configuracion": configuracion[14],
        "col_stock_configuracion": configuracion[7],
        "fila_comienzo_configuracion": configuracion[8],
        "separador_csv_configuracion": configuracion[9],
        "id_marca": configuracion[10],
        "id_configuracion": (
            configuracion[15] if len(configuracion) > 15 else None
        ),
    }
    config_descarga = {
        "ftp_server": configuracion[0],
        "ftp_port": configuracion[1],
        "ftp_user": configuracion[2],
        "ftp_pass": configuracion[3],
        "fichero_configuracion": configuracion[4],
        "http_configuracion": configuracion[11],
        "extension_configuracion": configuracion[5],
    }
    return excel_config, config_descarga


def _preparar_disponibilidad(df):
    resultado = df.copy()
    resultado.rename(columns={"source": "table"}, inplace=True)
    resultado["reference"] = normalizar_serie_identificadores(
        resultado["reference"]
    )
    identificadores_invalidos = int(resultado["reference"].isna().sum())
    if identificadores_invalidos:
        logging.warning(
            "Se excluyen %s coincidencias sin referencia válida para evitar "
            "actualizaciones SQL ambiguas",
            identificadores_invalidos,
        )
        resultado = resultado[resultado["reference"].notna()].copy()
    resultado["quantity"] = pd.to_numeric(
        resultado["quantity"], errors="coerce"
    ).fillna(0)
    resultado["hay_stock"] = pd.to_numeric(
        resultado["hay_stock"], errors="coerce"
    ).fillna(0)
    resultado["disponible"] = calcular_disponibilidad_series(
        resultado["quantity"],
        resultado["hay_stock"],
    )
    # Compatibilidad temporal: todas las funciones existentes reciben ahora
    # exclusivamente 0 o 1, nunca una suma de cantidades heterogéneas.
    resultado["stock_combinado"] = resultado["disponible"]
    resultado["es_fuente_catalogo"] = True
    return resultado


def _añadir_combinaciones_del_producto(
    df_fusionado,
    conexion_prestashop,
    id_proveedor,
    metricas,
):
    id_products = df_fusionado["id_product"].dropna().unique().tolist()
    if not id_products:
        return df_fusionado

    placeholders = ",".join(["%s"] * len(id_products))
    query = f"""
        SELECT pa.id_product, pa.id_product_attribute, pa.reference, sa.quantity
        FROM ps_product_attribute pa
        INNER JOIN ps_stock_available sa
            ON sa.id_product_attribute = pa.id_product_attribute
           AND sa.id_shop = 1
        WHERE pa.id_product IN ({placeholders})
    """
    with metricas.medir("Consultas SQL"):
        with conexion_prestashop.cursor() as cursor:
            cursor.execute(query, id_products)
            rows = cursor.fetchall()

    extra_df = pd.DataFrame(
        rows,
        columns=[
            "id_product",
            "id_product_attribute",
            "reference",
            "quantity",
        ],
    )
    if extra_df.empty:
        return df_fusionado

    extra_df["reference"] = normalizar_serie_identificadores(
        extra_df["reference"]
    )
    extra_df = extra_df[extra_df["reference"].notna()].copy()
    extra_df["table"] = "ps_product_attribute"
    # Estas filas completan el mapa de tallas usando el stock físico actual
    # de PrestaShop. No son una coincidencia de catálogo y, por ello, nunca
    # conceden permiso para modificar id_shop.
    extra_df["id_proveedor"] = 0
    extra_df["es_fuente_catalogo"] = False
    extra_df["hay_stock"] = 0
    extra_df["disponible"] = (
        pd.to_numeric(extra_df["quantity"], errors="coerce").fillna(0) > 0
    ).astype("int8")
    extra_df["stock_combinado"] = extra_df["disponible"]

    atributos_existentes = set(
        pd.to_numeric(
            df_fusionado.get("id_product_attribute"),
            errors="coerce",
        ).dropna().astype(int)
    )
    extra_df = extra_df[
        ~extra_df["id_product_attribute"].isin(atributos_existentes)
    ]
    resultado = pd.concat([df_fusionado, extra_df], ignore_index=True)
    return resultado.drop_duplicates(
        subset=["id_product", "id_product_attribute", "table"],
        keep="first",
    )


def _actualizar_prestashop(
    conexion_prestashop,
    conexion_proveedores,
    prestashop_df,
    df_fusionado,
    id_proveedor,
    metricas,
    solo_previsualizar=False,
):
    # Compatibilidad para consumidores aislados: incluso una sola fuente usa
    # el mismo constructor de plan que el lote operativo.
    with metricas.medir("Resolución global PrestaShop"):
        plan = construir_plan_global(
            conexion_prestashop,
            conexion_proveedores,
            df_fusionado,
        )
    if solo_previsualizar:
        return plan
    with metricas.medir("Aplicación plan global PrestaShop"):
        return aplicar_plan_global(conexion_prestashop, plan)


def _leer_fuente_local_validacion():
    """Lee el fichero fijado para que ambas ejecuciones usen los mismos bytes."""

    valor = os.environ.get("STOCK_VALIDATION_SOURCE_FILE")
    if not valor:
        return None
    raiz = Path(__file__).resolve().parent.parent
    carpeta_permitida = (raiz / "tmp").resolve()
    ruta = Path(valor)
    if not ruta.is_absolute():
        ruta = (raiz / ruta).resolve()
    else:
        ruta = ruta.resolve()
    try:
        ruta.relative_to(carpeta_permitida)
    except ValueError as error:
        raise RuntimeError(
            "STOCK_VALIDATION_SOURCE_FILE debe estar dentro de tmp/"
        ) from error
    if not ruta.is_file():
        raise RuntimeError(f"No existe el fichero local de validación: {ruta}")
    contenido = ruta.read_bytes()
    if not contenido:
        raise RuntimeError("El fichero local de validación está vacío")
    logging.info(
        "Usando fichero local fijado para validación (%s bytes)",
        len(contenido),
    )
    return contenido


def _guardar_fuente_validacion(contenido: bytes) -> None:
    """Fija fuera de Git los bytes descargados para poder repetir la prueba."""

    valor = os.environ.get("STOCK_VALIDATION_CAPTURE_FILE")
    if not valor:
        return
    raiz = Path(__file__).resolve().parent.parent
    carpeta_permitida = (raiz / "tmp").resolve()
    ruta = Path(valor)
    ruta = (
        (raiz / ruta).resolve()
        if not ruta.is_absolute()
        else ruta.resolve()
    )
    try:
        ruta.relative_to(carpeta_permitida)
    except ValueError as error:
        raise RuntimeError(
            "STOCK_VALIDATION_CAPTURE_FILE debe estar dentro de tmp/"
        ) from error
    if ruta.exists():
        if ruta.read_bytes() != contenido:
            raise RuntimeError(
                "El fichero capturado ya existe con contenido diferente"
            )
        return
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    logging.info("Fichero de validación fijado (%s bytes)", len(contenido))


def _combinar_variantes_cargas(cargas, id_proveedor):
    """Revalida solo cuando hay varios ficheros que puedan solaparse."""

    if len(cargas) == 1:
        return cargas[0]["dataframe"].copy()
    variantes = pd.concat(
        [carga["dataframe"] for carga in cargas],
        ignore_index=True,
    )
    return preparar_variantes_o_fallar(
        variantes,
        id_proveedor=id_proveedor,
        identificadores_normalizados=True,
    )


def _cargar_historico_marcas_multiples(
    conexion_proveedores,
    id_proveedor,
):
    """Carga solo la identidad histórica necesaria para un fallback exacto."""

    with conexion_proveedores.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id_marca,
                referencia_producto,
                ean_producto,
                estado_clasificacion_marca
            FROM productos_variantes
            WHERE id_proveedor = %s
            """,
            (id_proveedor,),
        )
        filas = cursor.fetchall()
    return pd.DataFrame(
        filas,
        columns=[
            "id_marca",
            "referencia_producto",
            "ean_producto",
            "estado_clasificacion_marca",
        ],
    )


def _leer_fuente_configuracion(
    almacen_fuentes,
    id_proveedor,
    numero,
    identidad_fuente,
    identidad_configuracion,
):
    """Reutiliza una asignacion preparada incluso durante una captura mixta."""

    if almacen_fuentes is None:
        return _leer_fuente_local_validacion()
    if (
        almacen_fuentes.modo == MODO_CAPTURA
        and not almacen_fuentes.contiene(id_proveedor, numero)
    ):
        return None
    return almacen_fuentes.leer(
        id_proveedor,
        numero,
        nombre_original=identidad_fuente,
        identidad_configuracion=identidad_configuracion,
    )


def _procesar_proveedor(
    id_proveedor,
    conexion_proveedores,
    conexion_prestashop,
    prestashop_df,
    resultado_ejecucion,
    metricas,
    solo_previsualizar_prestashop=False,
    almacen_fuentes=None,
    registrar_candidatos=None,
    registrar_resolucion_marcas=None,
):
    with metricas.medir("Carga de configuración"):
        configuraciones = obtener_configuraciones_proveedor(
            id_proveedor,
            conexion_proveedores,
        )
    if not configuraciones:
        raise ValueError(
            f"El proveedor {id_proveedor} no tiene una configuración válida"
        )

    cargas = []
    for numero, configuracion in enumerate(configuraciones, start=1):
        excel_config, config_descarga = _extraer_configuracion(
            configuracion,
            id_proveedor,
            numero,
        )
        id_configuracion = excel_config.get("id_configuracion")
        marcas_multiples = (
            obtener_marcas_permitidas_configuracion(
                id_configuracion,
                conexion_proveedores,
            )
            if id_configuracion is not None
            else []
        )
        resolucion_configurada = (
            obtener_resolucion_marca_configuracion(
                id_configuracion,
                conexion_proveedores,
            )
            if id_configuracion is not None
            else None
        )
        if resolucion_configurada:
            excel_config.update(resolucion_configurada)
        if marcas_multiples:
            if len(marcas_multiples) < 2 and not resolucion_configurada:
                raise ValueError(
                    f"Configuración multipmarca {id_configuracion} incompleta"
                )
            excel_config["marcas_multiples"] = [
                {
                    "id_marca": marca["id_marca"],
                    "nombre_marca_prestashop": marca[
                        "nombre_marca_prestashop"
                    ],
                    "prioridad": marca["prioridad"],
                }
                for marca in marcas_multiples
            ]
        # Las lecturas de configuración no deben mantener una transacción
        # abierta durante la descarga remota.
        conexion_proveedores.rollback()
        identidad_fuente = config_descarga.get(
            "fichero_configuracion"
        ) or config_descarga.get("http_configuracion")
        identidad_excel = {
            clave: valor
            for clave, valor in excel_config.items()
            if clave != "id_configuracion"
        }
        identidad_configuracion = calcular_identidad_configuracion(
            identidad_excel,
            config_descarga,
        )
        with metricas.medir("Descarga"):
            archivo_bytes = _leer_fuente_configuracion(
                almacen_fuentes,
                id_proveedor,
                numero,
                identidad_fuente,
                identidad_configuracion,
            )
            if archivo_bytes is None:
                archivo_bytes, configuracion_excel = (
                    descargar_y_procesar_archivo(
                        config_descarga,
                        excel_config,
                        id_proveedor,
                        conexion_proveedores,
                    )
                )
                if archivo_bytes is not None:
                    if almacen_fuentes is None:
                        _guardar_fuente_validacion(archivo_bytes)
                    else:
                        almacen_fuentes.capturar(
                            id_proveedor,
                            numero,
                            archivo_bytes,
                            nombre_original=identidad_fuente,
                            identidad_configuracion=identidad_configuracion,
                        )
            else:
                configuracion_excel = excel_config
        if archivo_bytes is None:
            raise RuntimeError(
                f"No se descargó el fichero de la configuración {numero}"
            )

        with metricas.medir("Procesamiento del fichero"):
            df_procesado = procesar_archivo_excel(
                archivo_bytes,
                id_proveedor,
                configuracion_excel["id_marca"],
                conexion_proveedores,
                configuracion_excel,
                metricas=metricas,
            )
        if df_procesado is None or df_procesado.empty:
            raise RuntimeError(
                f"El fichero de la configuración {numero} no produjo filas válidas"
            )

        resolucion_multipmarca = None
        if marcas_multiples:
            historico = _cargar_historico_marcas_multiples(
                conexion_proveedores,
                id_proveedor,
            )
            resolucion_multipmarca = resolver_marcas_multiples(
                df_procesado,
                prestashop_df,
                marcas_permitidas=marcas_multiples,
                id_marca_pendiente=configuracion_excel.get(
                    "id_marca_pendiente",
                    configuracion_excel["id_marca"],
                ),
                id_configuracion=id_configuracion,
                historico_df=historico,
            )
            if not resolucion_multipmarca.conflictos.empty:
                logging.warning(
                    "Proveedor %s, configuracion %s: se omiten %s filas con "
                    "conflictos de identidad en PrestaShop",
                    id_proveedor,
                    numero,
                    len(resolucion_multipmarca.conflictos),
                )
            if not resolucion_multipmarca.fuera_marcas_permitidas.empty:
                logging.warning(
                    "Proveedor %s, configuracion %s: se omiten %s "
                    "coincidencias cuya marca PrestaShop no esta autorizada",
                    id_proveedor,
                    numero,
                    len(resolucion_multipmarca.fuera_marcas_permitidas),
                )
            if registrar_resolucion_marcas is not None:
                registrar_resolucion_marcas(
                    id_proveedor,
                    numero,
                    resolucion_multipmarca.auditoria.copy(),
                )
            df_procesado = resolucion_multipmarca.dataframe
            marcas_permitidas = [
                marca["nombre_marca_prestashop"]
                for marca in marcas_multiples
            ]
        else:
            with conexion_proveedores.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT nombre_marca
                    FROM marcas
                    WHERE id_marca = %s
                      AND nombre_marca IS NOT NULL
                      AND TRIM(nombre_marca) <> ''
                    """,
                    (configuracion_excel["id_marca"],),
                )
                marcas_permitidas = [fila[0] for fila in cursor.fetchall()]
        if not marcas_permitidas:
            raise ValueError(
                "No existe una marca válida para la configuración "
                f"{numero} del proveedor {id_proveedor}"
            )

        df_procesado = df_procesado.copy()
        if not marcas_multiples:
            df_procesado["id_marca"] = configuracion_excel["id_marca"]
        cargas.append(
            {
                "numero": numero,
                "dataframe": df_procesado,
                "marcas": marcas_permitidas,
                "es_multipmarca": bool(marcas_multiples),
                "resolucion_multipmarca": resolucion_multipmarca,
                "estadisticas_preparacion": df_procesado.attrs.get(
                    "estadisticas_variantes",
                    {},
                ),
            }
        )

    # No se marca ninguna variante ausente hasta que todos los ficheros del
    # proveedor se han descargado, leído y validado correctamente.
    variantes_proveedor = _combinar_variantes_cargas(
        cargas,
        id_proveedor,
    )
    with metricas.medir("Persistencia de variantes y resúmenes"):
        persistencia = persistir_variantes_y_resumen(
            conexion_proveedores,
            variantes_proveedor,
            id_proveedor=id_proveedor,
            id_marca=None,
        )
    logging.info(
        "Proveedor %s: persistencia atómica de %s configuraciones: %s",
        id_proveedor,
        len(cargas),
        persistencia.como_dict(),
    )

    # Una fuente grande puede mantener inactiva la conexión de PrestaShop
    # durante varios minutos. Se reconecta antes del primer cruce que pueda
    # consultar o escribir, y se comprueba de nuevo la base autorizada.
    _asegurar_conexion_activa(
        conexion_prestashop,
        BASE_PRESTASHOP_ACTIVA,
        "PrestaShop",
    )

    informes_configuracion = []
    for carga in cargas:
        numero = carga["numero"]
        df_procesado = carga["dataframe"]
        marcas_permitidas = carga["marcas"]
        proveedor_df = crear_tabla_aux_proveedor(df_procesado)
        resolucion_multipmarca = carga["resolucion_multipmarca"]
        if carga["es_multipmarca"]:
            df_fusionado = resolucion_multipmarca.coincidencias.copy()
            estadisticas_cruce = {
                **resolucion_multipmarca.estadisticas.como_dict(),
                "fabricantes": {
                    str(marca): int(total)
                    for marca, total in resolucion_multipmarca.auditoria.loc[
                        resolucion_multipmarca.auditoria["estado"] == "resuelta",
                        "marca_prestashop",
                    ].value_counts().items()
                },
            }
            if "referencia_alternativa" in df_procesado.columns:
                logging.info(
                    "Cruce proveedor %s, configuracion %s: "
                    "referencia_principal=%s, referencia_alternativa=%s, "
                    "EAN=%s, sin_coincidencia=%s, ambiguas_alt=%s, "
                    "conflictos=%s",
                    id_proveedor,
                    numero,
                    estadisticas_cruce.get("resueltas_referencia", 0),
                    estadisticas_cruce.get(
                        "resueltas_referencia_alternativa", 0
                    ),
                    estadisticas_cruce.get("resueltas_ean", 0),
                    estadisticas_cruce.get("sin_coincidencia", 0),
                    estadisticas_cruce.get(
                        "referencias_alternativas_ambiguas", 0
                    ),
                    estadisticas_cruce.get("conflictos_identificadores", 0),
                )
        else:
            df_fusionado = comparar_tablas_auxiliares(
                prestashop_df,
                proveedor_df,
                id_proveedor=id_proveedor,
                marcas_permitidas=marcas_permitidas,
                metricas=metricas,
            )
            estadisticas_cruce = df_fusionado.attrs.get(
                "estadisticas_cruce",
                {},
            )
        informe_configuracion = {
            "configuracion": numero,
            "preparacion_variantes": carga["estadisticas_preparacion"],
            "persistencia": persistencia.como_dict(),
            "cruce": estadisticas_cruce,
            "multipmarca": carga["es_multipmarca"],
        }
        informes_configuracion.append(informe_configuracion)
        if df_fusionado is None or df_fusionado.empty:
            logging.info(
                "Proveedor %s, configuración %s: coincidencias "
                "PrestaShop=0, cambios PrestaShop=0",
                id_proveedor,
                numero,
            )
            informe_configuracion["prestashop"] = {
                "objetivos": 0,
                "cambios_funcionales": 0,
                "aplica_cambios": False,
            }
            continue

        df_fusionado["id_proveedor"] = id_proveedor
        df_fusionado = _preparar_disponibilidad(df_fusionado)
        if df_fusionado.empty:
            mensaje = (
                f"Proveedor {id_proveedor}, configuración {numero}: "
                "las coincidencias no tenían una referencia SQL válida"
            )
            resultado_ejecucion.advertir("Cruce de catálogos", mensaje)
            logging.warning(mensaje)
            continue
        df_fusionado = _añadir_combinaciones_del_producto(
            df_fusionado,
            conexion_prestashop,
            id_proveedor,
            metricas,
        )
        if not carga["es_multipmarca"]:
            df_fusionado = añadir_referencias_colgadas(
                df_fusionado,
                conexion_prestashop,
                conexion_proveedores,
                id_proveedor,
            )
        if registrar_candidatos is not None:
            registrar_candidatos(
                id_proveedor,
                numero,
                df_fusionado,
                marcas_permitidas,
            )
        # Fase A: el proveedor termina y deja intenciones exactas. PrestaShop
        # no se decide ni se modifica hasta que hayan terminado todos.
        resultado_ejecucion.intenciones_prestashop.append(
            df_fusionado.copy()
        )
        destinos = df_fusionado[
            ["id_product", "id_product_attribute"]
        ].drop_duplicates()
        informe_configuracion["prestashop"] = {
            "intenciones": int(len(destinos)),
            "objetivos": int(len(destinos)),
            "cambios_funcionales": 0,
            "aplica_cambios": False,
            "resolucion_diferida": True,
        }
    return informes_configuracion


def _validar_base_activa(conexion, base_esperada, etiqueta):
    if not base_esperada:
        return
    with conexion.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        fila = cursor.fetchone()
    base_activa = fila[0] if fila else None
    if base_activa != base_esperada:
        raise RuntimeError(
            f"Base {etiqueta} inesperada: {base_activa!r}; "
            f"se esperaba {base_esperada!r}"
        )


def _asegurar_conexion_activa(conexion, base_esperada, etiqueta):
    """Reconecta una sesión inactiva y vuelve a validar su base efectiva."""

    ping = getattr(conexion, "ping", None)
    if not callable(ping):
        return
    ping(reconnect=True)
    _validar_base_activa(conexion, base_esperada, etiqueta)


def _aplicar_plan_con_trazabilidad(
    conexion_prestashop,
    plan_global,
    *,
    execution_id,
    modo,
    ruta_plan,
):
    """Aplica el plan ya persistido y publica un resultado separado."""

    try:
        aplicacion = aplicar_plan_global(conexion_prestashop, plan_global)
    except Exception as error:
        persistir_resultado_ejecucion(
            execution_id=execution_id,
            modo=modo,
            ruta_plan=ruta_plan,
            success=False,
            error_tipo=type(error).__name__,
        )
        raise
    registrar_acciones_humanas(plan_global, modo=modo)
    ruta_resultado = persistir_resultado_ejecucion(
        execution_id=execution_id,
        modo=modo,
        ruta_plan=ruta_plan,
        success=True,
        filas_modificadas=getattr(aplicacion, "filas_modificadas", 0),
        rowcount=getattr(aplicacion, "filas_modificadas", 0),
        commits=getattr(aplicacion, "commits", 0),
    )
    return aplicacion, ruta_resultado


def main(
    id_proveedores=None,
    *,
    ejecutar_huerfanos=False,
    ejecutar_obsoletos=False,
    ejecutar_visibilidad=False,
    enviar_notificacion=True,
    prefijo_asunto="",
    base_prestashop_esperada=BASE_PRESTASHOP_ACTIVA,
    base_proveedores_esperada=BASE_PROVEEDORES_ACTIVA,
    solo_previsualizar_prestashop=False,
    autorizar_lote_validacion=False,
    detener_en_primer_fallo=False,
    refrescar_prestashop_entre_proveedores=False,
    comprobar_seguridad_entre_proveedores=None,
    registrar_candidatos=None,
    registrar_resolucion_marcas=None,
    bloqueo_operativo_externo=None,
    autorizar_bloqueo_externo_aislado=False,
):
    inicio = time.perf_counter()
    execution_id = nuevo_execution_id()
    modo_trazabilidad = (
        "report-only" if solo_previsualizar_prestashop else "apply"
    )
    validar_entorno_configurado()
    if id_proveedores is None:
        id_proveedores = [25]
    else:
        id_proveedores = list(id_proveedores)
    if not id_proveedores:
        raise ValueError("Debe indicarse al menos un proveedor")
    es_lote_validacion = (
        autorizar_lote_validacion
        and es_entorno_prueba_proveedores_operativos()
        and tuple(id_proveedores) == PROVEEDORES_OPERATIVOS_VALIDACION
        and base_prestashop_esperada == BASE_PRESTASHOP_PRUEBAS_REMOTA
        and base_proveedores_esperada == BASE_PROVEEDORES_OPERATIVA
    )
    if autorizar_lote_validacion and not es_lote_validacion:
        raise ValueError(
            "El lote solo admite el perfil, las bases y la lista exactos"
        )
    if not es_entorno_operativo() and len(id_proveedores) != 1 and not (
        es_lote_validacion
    ):
        raise ValueError(
            "La validación aislada exige exactamente un proveedor"
        )
    if es_lote_validacion and any(
        (ejecutar_huerfanos, ejecutar_obsoletos, ejecutar_visibilidad)
    ):
        raise ValueError("El lote no permite ejecutar fases globales")
    if es_lote_validacion and not callable(
        comprobar_seguridad_entre_proveedores
    ):
        raise ValueError("El lote exige la comprobacion externa de procesos")
    if es_lote_validacion and not callable(registrar_candidatos):
        raise ValueError("El lote exige una auditoria de candidatos")
    bloqueo_externo_aislado_valido = (
        autorizar_bloqueo_externo_aislado
        and es_entorno_prueba_proveedores_operativos()
        and len(id_proveedores) == 1
        and base_prestashop_esperada == BASE_PRESTASHOP_PRUEBAS_REMOTA
        and base_proveedores_esperada == BASE_PROVEEDORES_OPERATIVA
    )
    if bloqueo_operativo_externo is not None and not (
        es_lote_validacion or bloqueo_externo_aislado_valido
    ):
        raise ValueError(
            "El bloqueo externo exige un lote cerrado o una validación "
            "aislada autorizada"
        )
    conexiones = []
    resultado = ResultadoEjecucion()
    metricas_globales = MetricasRendimiento("Ejecución completa")
    conexion_proveedores = None
    conexion_prestashop = None
    bloqueo_operativo = None
    plan_global = None
    ruta_plan = None
    ruta_resultado = None
    ruta_informe = None
    contenido_plan = None

    if es_lote_validacion:
        comprobar_seguridad_entre_proveedores()

    try:
        with metricas_globales.medir("Conexión a bases"):
            conexion_proveedores = conectar_proveedores()
            if conexion_proveedores is not None:
                conexiones.append(
                    (conexion_proveedores, TIPO_PROVEEDORES)
                )
            conexion_prestashop = conectar_prestashop()
            if conexion_prestashop is not None:
                conexiones.append((conexion_prestashop, TIPO_PRESTASHOP))
        if conexion_proveedores is None or conexion_prestashop is None:
            raise ConnectionError("No se pudieron abrir las dos conexiones")
        _validar_base_activa(
            conexion_prestashop,
            base_prestashop_esperada,
            "PrestaShop",
        )
        _validar_base_activa(
            conexion_proveedores,
            base_proveedores_esperada,
            "proveedores",
        )
        if (
            es_entorno_operativo()
            or es_entorno_prueba_proveedores_operativos()
        ):
            if es_entorno_operativo():
                validar_preflight_operativo(
                    conexion_prestashop,
                    conexion_proveedores,
                )
            else:
                validar_preflight_prueba_proveedores_operativos(
                    conexion_prestashop,
                    conexion_proveedores,
                )
            if bloqueo_operativo_externo is not None:
                bloqueo_operativo_externo.validar_propiedad()
            else:
                bloqueo_operativo = BloqueoEjecucionOperativa(
                    conexion_proveedores,
                    timeout_segundos=5,
                )
                bloqueo_operativo.adquirir()

        with metricas_globales.medir("Consulta inicial de PrestaShop"):
            prestashop_df = crear_tabla_aux_prestashop(conexion_prestashop)
        almacen_fuentes = AlmacenFuentesValidacion.desde_entorno()

        for indice, id_proveedor in enumerate(id_proveedores):
            metricas_proveedor = MetricasRendimiento(
                f"Proveedor {id_proveedor}"
            )
            advertencias_antes = len(resultado.advertencias)
            proveedor_correcto = False
            try:
                logging.info("Procesando proveedor con ID: %s", id_proveedor)
                logger_funciones_especificas.info(
                    "Procesando proveedor con ID: %s",
                    id_proveedor,
                )
                with metricas_proveedor.medir("Total"):
                    detalles = _procesar_proveedor(
                        id_proveedor,
                        conexion_proveedores,
                        conexion_prestashop,
                        prestashop_df,
                        resultado,
                        metricas_proveedor,
                        solo_previsualizar_prestashop,
                        almacen_fuentes,
                        registrar_candidatos,
                        registrar_resolucion_marcas,
                    )
                # Una actualizacion extensa de PrestaShop puede superar el
                # wait_timeout de la sesion de proveedores. La reactivamos y
                # revalidamos su destino antes de auditar o continuar.
                _asegurar_conexion_activa(
                    conexion_proveedores,
                    base_proveedores_esperada,
                    "proveedores",
                )
                resultado.detalles_proveedores[id_proveedor] = detalles
                if es_lote_validacion:
                    _validar_base_activa(
                        conexion_prestashop,
                        BASE_PRESTASHOP_PRUEBAS_REMOTA,
                        "PrestaShop",
                    )
                    _validar_base_activa(
                        conexion_proveedores,
                        BASE_PROVEEDORES_OPERATIVA,
                        "proveedores",
                    )
                    comprobar_seguridad_entre_proveedores()
                    if bloqueo_operativo_externo is not None:
                        bloqueo_operativo_externo.validar_propiedad()
                resultado.proveedor_correcto(id_proveedor)
                proveedor_correcto = (
                    len(resultado.advertencias) == advertencias_antes
                )
            except Exception as error:
                logging.exception(
                    "Error crítico procesando proveedor %s",
                    id_proveedor,
                )
                resultado.proveedor_fallido(id_proveedor, str(error))
            finally:
                resultado.metricas_proveedores[id_proveedor] = {
                    "segundos": dict(metricas_proveedor._duraciones),
                    "conteos": dict(metricas_proveedor._conteos),
                }
                metricas_proveedor.registrar_resumen()
            if detener_en_primer_fallo and not proveedor_correcto:
                logging.error(
                    "Lote detenido tras el proveedor %s por estado no SUCCESS",
                    id_proveedor,
                )
                break
            if (
                proveedor_correcto
                and refrescar_prestashop_entre_proveedores
                and indice < len(id_proveedores) - 1
            ):
                with metricas_globales.medir(
                    "Refresco de PrestaShop entre proveedores"
                ):
                    prestashop_df = crear_tabla_aux_prestashop(
                        conexion_prestashop
                    )

        # Fase B/C: una única resolución global y un único plan para ambos
        # modos. No se toma ninguna decisión PrestaShop con una carga incompleta.
        if resultado.estado is EstadoEjecucion.SUCCESS:
            intenciones = (
                pd.concat(
                    resultado.intenciones_prestashop,
                    ignore_index=True,
                    sort=False,
                )
                if resultado.intenciones_prestashop
                else pd.DataFrame(
                    columns=[
                        "id_product",
                        "id_product_attribute",
                        "stock_combinado",
                    ]
                )
            )
            with metricas_globales.medir("Resolución global PrestaShop"):
                plan_global = construir_plan_global(
                    conexion_prestashop,
                    conexion_proveedores,
                    intenciones,
                    incluir_visibilidad=ejecutar_visibilidad,
                )
            # La publicacion atomica del plan es anterior a la rama que puede
            # ejecutar UPDATE; si falla, no se intenta aplicar nada.
            ruta_plan, contenido_plan = persistir_plan_detallado(
                plan_global,
                execution_id=execution_id,
                modo=modo_trazabilidad,
            )
            datos_plan = plan_global.como_dict()
            datos_plan.update(
                {
                    "execution_id": execution_id,
                    "modo": modo_trazabilidad,
                    "plan_detallado": str(ruta_plan),
                }
            )
            resultado.plan_prestashop = datos_plan
            if solo_previsualizar_prestashop:
                resultado.fases_globales["prestashop"] = "REPORT-ONLY"
                registrar_acciones_humanas(
                    plan_global,
                    modo=modo_trazabilidad,
                )
                ruta_resultado = persistir_resultado_ejecucion(
                    execution_id=execution_id,
                    modo=modo_trazabilidad,
                    ruta_plan=ruta_plan,
                    success=True,
                )
                resultado.plan_prestashop["resultado_ejecucion"] = str(
                    ruta_resultado
                )
                logging.info("Plan global PrestaShop: %s", datos_plan)
            else:
                with metricas_globales.medir(
                    "Aplicación plan global PrestaShop"
                ):
                    aplicacion, ruta_resultado = _aplicar_plan_con_trazabilidad(
                        conexion_prestashop,
                        plan_global,
                        execution_id=execution_id,
                        modo=modo_trazabilidad,
                        ruta_plan=ruta_plan,
                    )
                datos_aplicacion = aplicacion.como_dict()
                datos_aplicacion.update(
                    {
                        "execution_id": execution_id,
                        "modo": modo_trazabilidad,
                        "plan_detallado": str(ruta_plan),
                        "resultado_ejecucion": str(ruta_resultado),
                    }
                )
                resultado.plan_prestashop = datos_aplicacion
                resultado.fases_globales["prestashop"] = "APLICADA"
                logging.info(
                    "Plan global PrestaShop aplicado: %s",
                    datos_aplicacion,
                )
            if ejecutar_visibilidad:
                resultado.fases_globales["visibilidad"] = (
                    "REPORT-ONLY"
                    if solo_previsualizar_prestashop
                    else "APLICADA"
                )

        # No se toman decisiones globales destructivas con una carga incompleta.
        fases_globales_solicitadas = any(
            (ejecutar_huerfanos, ejecutar_obsoletos, ejecutar_visibilidad)
        )
        if resultado.estado is EstadoEjecucion.SUCCESS:
            if ejecutar_huerfanos:
                try:
                    with metricas_globales.medir("Huérfanos"):
                        detectar_referencias_huerfanas_para_desactivar(
                            conexion_prestashop,
                            conexion_proveedores,
                            metricas=metricas_globales,
                        )
                except Exception as error:
                    logging.exception("Error en la fase global de huérfanos")
                    resultado.advertir("Huérfanos", str(error))

            if ejecutar_obsoletos:
                try:
                    with metricas_globales.medir("Obsoletos"):
                        detectar_productos_obsoletos_para_desactivar(
                            conexion_prestashop,
                            conexion_proveedores,
                            metricas=metricas_globales,
                        )
                except Exception as error:
                    logging.exception("Error en la fase global de obsoletos")
                    resultado.advertir("Obsoletos", str(error))

            if not fases_globales_solicitadas:
                logging.info(
                    "Fases globales omitidas por configuración explícita"
                )
        else:
            if ejecutar_visibilidad:
                resultado.fases_globales["visibilidad"] = "OMITIDA"
            fases = []
            if ejecutar_huerfanos:
                fases.append("huérfanos")
            if ejecutar_obsoletos:
                fases.append("obsoletos")
            if ejecutar_visibilidad:
                fases.append("visibilidad")
            logging.warning(
                "Se omiten las fases globales solicitadas porque la carga "
                "no terminó en SUCCESS: %s",
                ", ".join(fases) if fases else "ninguna",
            )

    except Exception as error:
        logging.exception("Error crítico global en main")
        resultado.fallo_global("Ejecución global", str(error))

    finally:
        logging.info("Cerrando conexiones a bases de datos")
        if bloqueo_operativo is not None:
            bloqueo_operativo.liberar()
        for conexion, tipo_conexion in conexiones:
            cerrar_conexion(conexion, tipo_conexion=tipo_conexion)

        try:
            with metricas_globales.medir("Informe de cambios"):
                ruta_informe = persistir_informe_cambios(
                    contenido_plan,
                    execution_id=execution_id,
                    modo=modo_trazabilidad,
                    resultado=resultado.estado.value,
                    cambios_aplicados=(
                        modo_trazabilidad == "apply"
                        and ruta_resultado is not None
                    ),
                    proveedores_fallidos=sorted(
                        resultado.proveedores_fallidos
                    ),
                    errores=[
                        ocultar_secretos(
                            error,
                            {
                                prestashop_config.get("password", ""),
                                proveedores_config.get("password", ""),
                            },
                        )
                        for error in resultado.errores
                    ],
                )
            resultado.fases_globales["informe_cambios"] = "GENERADO"
        except Exception as error:
            logging.exception("No se pudo generar el informe de cambios")
            resultado.advertir("Informe de cambios", type(error).__name__)
            resultado.fases_globales["informe_cambios"] = "FALLIDO"

        duracion_sin_correo = time.perf_counter() - inicio
        rutas_log = rutas_logs()
        asunto, cuerpo = construir_notificacion(
            resultado,
            duracion_segundos=duracion_sin_correo,
            logs=[
                rutas_log["general"],
                rutas_log["resumen"],
                rutas_log["errores"],
            ],
            secretos={
                prestashop_config.get("password", ""),
                proveedores_config.get("password", ""),
            },
        )
        asunto = f"{prefijo_asunto}{asunto}"
        if ruta_informe is not None:
            cuerpo += (
                "\nInforme de cambios adjunto: "
                f"{nombre_visible_informe(ruta_informe)}"
            )
        correo_enviado = False
        if enviar_notificacion:
            with metricas_globales.medir("Correo"):
                correo_enviado = enviar_correo(
                    asunto=asunto,
                    cuerpo=cuerpo,
                    informe_cambios=ruta_informe,
                )
            resultado.fases_globales["notificacion"] = (
                "ENVIADA" if correo_enviado else "FALLIDA"
            )
        else:
            logging.info("Notificación por correo omitida por configuración")
            resultado.fases_globales["notificacion"] = "OMITIDA"

        # La limpieza siempre es posterior al informe y a su notificación.
        # Un fallo de correo conserva tanto el informe como toda la evidencia.
        if correo_enviado and ruta_informe is not None:
            protegidos = [
                ruta_plan,
                ruta_resultado,
                ruta_informe,
                *rutas_log.values(),
            ]
            if ruta_plan is not None:
                nombre_plan = Path(ruta_plan).name
                if nombre_plan.endswith("_plan.json"):
                    protegidos.append(
                        Path(ruta_plan).with_name(
                            f"{nombre_plan[:-len('_plan.json')]}_resultado.json"
                        )
                    )
            try:
                with metricas_globales.medir("Retención de logs"):
                    resumen_retencion = limpiar_archivos_antiguos(
                        dias=7,
                        protegidos=protegidos,
                    )
                resultado.fases_globales["retencion"] = (
                    "COMPLETADA"
                    if not resumen_retencion["errores"]
                    else "PARCIAL"
                )
                logging.info("Retención Stock3: %s", resumen_retencion)
            except Exception:
                logging.exception("No se pudo completar la retención Stock3")
                resultado.fases_globales["retencion"] = "FALLIDA"
        else:
            resultado.fases_globales["retencion"] = "OMITIDA"

        duracion_total = time.perf_counter() - inicio
        metricas_globales.registrar("Duración total", duracion_total)
        metricas_plan = dict(resultado.metricas_globales)
        resultado.metricas_globales = {
            "segundos": dict(metricas_globales._duraciones),
            "conteos": dict(metricas_globales._conteos),
            **metricas_plan,
        }
        metricas_globales.registrar_resumen()
        logging.info(
            "Estado final %s. Tiempo total: %.2f segundos",
            resultado.estado.value,
            duracion_total,
        )
        return resultado


if __name__ == "__main__":
    if es_entorno_operativo():
        raise SystemExit(
            "El perfil operativo solo puede ejecutarse mediante "
            "main_operativo.py con --report-only o --apply"
        )
    if es_entorno_validacion_remota():
        raise SystemExit(
            "Use main_validacion_remota.py para el perfil híbrido"
        )
    if es_entorno_prueba_proveedores_operativos():
        raise SystemExit(
            "Use main_prueba_proveedores_operativos.py para esta prueba"
        )
    if not PROVEEDORES_OPERATIVOS_VALIDACION:
        raise SystemExit("Configure STOCK_PROVIDER_IDS for the local test dataset.")
    main(
        list(PROVEEDORES_OPERATIVOS_VALIDACION),
        ejecutar_huerfanos=False,
        ejecutar_obsoletos=False,
        ejecutar_visibilidad=False,
        enviar_notificacion=False,
        prefijo_asunto="[TEST STOCK] ",
        base_prestashop_esperada=BASE_PRESTASHOP_LOCAL,
        base_proveedores_esperada=BASE_PROVEEDORES_LOCAL,
    )
