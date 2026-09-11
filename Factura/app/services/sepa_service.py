from datetime import datetime
import xml.etree.ElementTree as ET
import logging

from app.database.db import get_connection
from app.utils.config import REMESAS_DIR


# ==========================================================
# VALIDAR IBAN SIMPLE
# ==========================================================
def _validar_iban(iban):

    if not iban:
        return False

    iban = iban.replace(" ", "").upper()

    if len(iban) < 15 or len(iban) > 34:
        return False

    return True


# ==========================================================
# OBTENER FACTURAS PENDIENTES DE DOMICILIACION
# ==========================================================
def obtener_facturas_para_remesa():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            d.id,
            d.numero_legal,
            d.total,
            d.fecha_vencimiento,
            c.nombre,
            c.iban,
            c.mandato_sepa,
            c.fecha_mandato
        FROM documentos d
        JOIN clientes c ON c.id = d.cliente_id
        WHERE d.tipo = 'FACTURA'
        AND d.forma_pago = 'DOMICILIACION'
        AND d.estado_cobro = 'PENDIENTE'
        ORDER BY d.fecha_vencimiento ASC
        """
    )

    filas = cursor.fetchall()

    conn.close()

    return filas


# ==========================================================
# CREAR REMESA
# ==========================================================
def crear_remesa(facturas):

    conn = get_connection()
    cursor = conn.cursor()

    total = sum(f[2] for f in facturas)

    ahora = datetime.now()
    fecha = ahora.isoformat()

    # código único de remesa
    codigo_remesa = f"REMESA{ahora.strftime('%Y%m%d%H%M%S')}"

    cursor.execute(
        """
        INSERT INTO remesas (codigo_remesa, fecha, total, estado)
        VALUES (?, ?, ?, 'GENERADA')
        """,
        (codigo_remesa, fecha, total),
    )

    remesa_id = cursor.lastrowid

    for f in facturas:

        cursor.execute(
            """
            INSERT INTO remesa_lineas (remesa_id, factura_id, importe)
            VALUES (?, ?, ?)
            """,
            (remesa_id, f[0], f[2]),
        )

    conn.commit()
    conn.close()

    return remesa_id, codigo_remesa


# ==========================================================
# OBTENER DATOS EMPRESA
# ==========================================================
def obtener_empresa():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT nombre, iban_empresa, creditor_id, bic
        FROM empresa
        LIMIT 1
        """
    )

    empresa = cursor.fetchone()

    conn.close()

    if not empresa:
        raise Exception("No hay datos de empresa configurados")

    nombre, iban, creditor_id, bic = empresa

    if not _validar_iban(iban):
        raise Exception("IBAN de empresa no configurado o inválido")

    if not creditor_id:
        raise Exception("Creditor ID SEPA no configurado")

    return empresa


# ==========================================================
# GENERAR XML SEPA
# ==========================================================
def generar_xml_sepa(remesa_id, facturas, codigo_remesa):

    nombre_empresa, iban_empresa, creditor_id, bic = obtener_empresa()

    hoy = datetime.now()

    msg_id = codigo_remesa

    total = sum(f[2] for f in facturas)

    # Crear carpeta remesas
    REMESAS_DIR.mkdir(parents=True, exist_ok=True)

    filename = REMESAS_DIR / f"{msg_id}.xml"

    root = ET.Element(
        "Document",
        xmlns="urn:iso:std:iso:20022:tech:xsd:pain.008.001.02",
    )

    cstmr = ET.SubElement(root, "CstmrDrctDbtInitn")

    # ======================================================
    # GRUPO HEADER
    # ======================================================

    grp = ET.SubElement(cstmr, "GrpHdr")

    ET.SubElement(grp, "MsgId").text = msg_id
    ET.SubElement(grp, "CreDtTm").text = hoy.isoformat()
    ET.SubElement(grp, "NbOfTxs").text = str(len(facturas))
    ET.SubElement(grp, "CtrlSum").text = f"{total:.2f}"

    initg = ET.SubElement(grp, "InitgPty")
    ET.SubElement(initg, "Nm").text = nombre_empresa

    # ======================================================
    # PAYMENT INFO
    # ======================================================

    pmt = ET.SubElement(cstmr, "PmtInf")

    ET.SubElement(pmt, "PmtInfId").text = msg_id
    ET.SubElement(pmt, "PmtMtd").text = "DD"
    ET.SubElement(pmt, "NbOfTxs").text = str(len(facturas))
    ET.SubElement(pmt, "CtrlSum").text = f"{total:.2f}"

    pmt_tp = ET.SubElement(pmt, "PmtTpInf")

    svc = ET.SubElement(pmt_tp, "SvcLvl")
    ET.SubElement(svc, "Cd").text = "SEPA"

    lcl = ET.SubElement(pmt_tp, "LclInstrm")
    ET.SubElement(lcl, "Cd").text = "CORE"

    ET.SubElement(pmt_tp, "SeqTp").text = "RCUR"

    ET.SubElement(pmt, "ReqdColltnDt").text = hoy.strftime("%Y-%m-%d")

    # IMPORTANTE SEPA
    ET.SubElement(pmt, "ChrgBr").text = "SLEV"

    # ======================================================
    # CREDITOR
    # ======================================================

    cdtr = ET.SubElement(pmt, "Cdtr")
    ET.SubElement(cdtr, "Nm").text = nombre_empresa

    acct = ET.SubElement(pmt, "CdtrAcct")
    id_acct = ET.SubElement(acct, "Id")
    ET.SubElement(id_acct, "IBAN").text = iban_empresa

    agt = ET.SubElement(pmt, "CdtrAgt")
    fin = ET.SubElement(agt, "FinInstnId")

    if bic:
        ET.SubElement(fin, "BIC").text = bic
    else:
        ET.SubElement(fin, "Othr")

    schme = ET.SubElement(pmt, "CdtrSchmeId")
    sid = ET.SubElement(schme, "Id")
    prvt = ET.SubElement(sid, "PrvtId")
    othr = ET.SubElement(prvt, "Othr")

    ET.SubElement(othr, "Id").text = creditor_id

    # ======================================================
    # FACTURAS
    # ======================================================

    for f in facturas:

        (
            fid,
            numero,
            importe,
            fecha_venc,
            cliente,
            iban_cliente,
            mandato,
            fecha_mandato,
        ) = f

        if not _validar_iban(iban_cliente):

            logging.warning(
                f"Factura {numero} ignorada por IBAN inválido: {iban_cliente}"
            )

            continue

        tx = ET.SubElement(pmt, "DrctDbtTxInf")

        pmt_id = ET.SubElement(tx, "PmtId")
        ET.SubElement(pmt_id, "EndToEndId").text = numero

        amt = ET.SubElement(tx, "InstdAmt", Ccy="EUR")
        amt.text = f"{importe:.2f}"

        dbt = ET.SubElement(tx, "DrctDbtTx")
        mndt = ET.SubElement(dbt, "MndtRltdInf")

        ET.SubElement(mndt, "MndtId").text = mandato or numero
        ET.SubElement(mndt, "DtOfSgntr").text = fecha_mandato or hoy.strftime(
            "%Y-%m-%d"
        )

        dbtr = ET.SubElement(tx, "Dbtr")
        ET.SubElement(dbtr, "Nm").text = cliente

        dbtr_acct = ET.SubElement(tx, "DbtrAcct")
        id_acct = ET.SubElement(dbtr_acct, "Id")
        ET.SubElement(id_acct, "IBAN").text = iban_cliente

        # INFO FACTURA
        rmt = ET.SubElement(tx, "RmtInf")
        ET.SubElement(rmt, "Ustrd").text = f"Factura {numero}"

    # ======================================================
    # GUARDAR XML
    # ======================================================

    tree = ET.ElementTree(root)

    tree.write(filename, encoding="utf-8", xml_declaration=True)

    logging.info(f"SEPA XML generado: {filename}")

    # ======================================================
    # GUARDAR RUTA REMESA
    # ======================================================

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE remesas
        SET archivo_xml = ?
        WHERE id = ?
        """,
        (str(filename), remesa_id),
    )

    conn.commit()
    conn.close()

    return filename


# ==========================================================
# CREAR REMESA COMPLETA
# ==========================================================
def generar_remesa_sepa(facturas):

    if not facturas:
        raise Exception("No hay facturas seleccionadas para la remesa")

    remesa_id, codigo_remesa = crear_remesa(facturas)

    archivo = generar_xml_sepa(remesa_id, facturas, codigo_remesa)

    # 3️⃣ marcar facturas como EN_REMESA
    conn = get_connection()
    cursor = conn.cursor()

    for f in facturas:
        cursor.execute(
            """
            UPDATE documentos
            SET estado_cobro = 'EN_REMESA'
            WHERE id = ?
            """,
            (f[0],),
        )

    conn.commit()
    conn.close()

    return archivo
