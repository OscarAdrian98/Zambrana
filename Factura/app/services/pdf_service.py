from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from datetime import datetime
from app.database.db import get_connection
from app.services.empresa_service import obtener_empresa
import os
import logging
from app.utils.config import BASE_DIR


# ─────────────────────────────────────────────
# PALETA DE COLORES
# ─────────────────────────────────────────────
C_ACCENT = colors.HexColor("#2563EB")  # Azul corporativo
C_ACCENT_DARK = colors.HexColor("#1E40AF")
C_BG_HEADER = colors.HexColor("#F8FAFC")  # Fondo cabecera
C_BG_ROW_ALT = colors.HexColor("#F1F5F9")  # Fila alternada
C_BG_TOTAL = colors.HexColor("#EFF6FF")  # Fondo caja totales
C_BORDER = colors.HexColor("#CBD5E1")  # Bordes suaves
C_TEXT_DARK = colors.HexColor("#0F172A")  # Texto principal
C_TEXT_MID = colors.HexColor("#475569")  # Texto secundario
C_TEXT_LIGHT = colors.HexColor("#94A3B8")  # Texto pie
C_WHITE = colors.white
C_TABLE_HEAD = colors.HexColor("#1E3A5F")  # Cabecera tabla


# ─────────────────────────────────────────────
# COLOR DINÁMICO EMPRESA
# ─────────────────────────────────────────────
def _aplicar_color_empresa(empresa):
    """
    Permite cambiar el color corporativo del PDF según
    el color configurado en la empresa.
    """
    global C_ACCENT, C_ACCENT_DARK, C_TABLE_HEAD

    try:
        color_empresa = empresa[13] if len(empresa) > 13 else None

        if color_empresa:
            C_ACCENT = colors.HexColor(color_empresa)
            C_ACCENT_DARK = colors.HexColor(color_empresa)
            C_TABLE_HEAD = colors.HexColor(color_empresa)

    except Exception:
        pass


# ─────────────────────────────────────────────
# HELPERS BÁSICOS
# ─────────────────────────────────────────────
def _fmt_fecha_es(fecha_sql):
    if not fecha_sql:
        return ""
    try:
        return datetime.strptime(str(fecha_sql), "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return str(fecha_sql)


def _fmt_cantidad(cant):
    try:
        v = float(cant)
        return str(int(v)) if v.is_integer() else f"{v:.2f}"
    except Exception:
        return str(cant)


def _safe_str(value):
    return str(value) if value is not None else ""


def _draw_text(c, x, y, text, font="Helvetica", size=9, color=C_TEXT_DARK):
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawString(x, y, _safe_str(text))


def _draw_right(c, x, y, text, font="Helvetica", size=9, color=C_TEXT_DARK):
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawRightString(x, y, _safe_str(text))


def _draw_centered(c, cx, y, text, font="Helvetica", size=9, color=C_TEXT_DARK):
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawCentredString(cx, y, _safe_str(text))


def _split_text(c, text, max_width, font="Helvetica", size=9):
    text = _safe_str(text).strip()
    if not text:
        return []
    c.setFont(font, size)
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if c.stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _calc_logo_size(logo_path, max_w, max_h):
    """Calcula dimensiones manteniendo aspect ratio dentro del bounding box."""
    try:
        img = ImageReader(logo_path)
        iw, ih = img.getSize()
        if iw <= 0 or ih <= 0:
            return 0, 0
        ratio = min(max_w / iw, max_h / ih)
        return iw * ratio, ih * ratio
    except Exception:
        return 0, 0


def _crear_canvas_pdf(ruta_archivo):
    ruta_archivo.parent.mkdir(parents=True, exist_ok=True)
    return canvas.Canvas(str(ruta_archivo), pagesize=A4)


# ─────────────────────────────────────────────
# CONSTANTES DE LAYOUT
# ─────────────────────────────────────────────
MARGIN_X = 1.6 * cm
PAGE_W, PAGE_H = A4

# Anchura útil
CONTENT_W = PAGE_W - MARGIN_X * 2

# Columnas de la tabla (posiciones absolutas sobre la página)
COL_DESC_X = MARGIN_X + 0.3 * cm  # Descripción (izq)
COL_CANT_X = MARGIN_X + 9.8 * cm  # Cantidad (der)
COL_PRECIO_X = MARGIN_X + 12.6 * cm  # Precio unit. (der)
COL_IVA_X = MARGIN_X + 14.8 * cm  # IVA % (der)
COL_TOTAL_X = PAGE_W - MARGIN_X - 0.3 * cm  # Total línea (der)
COL_DESC_W = 9.0 * cm  # Ancho máx. descripción


# ─────────────────────────────────────────────
# NUEVA PÁGINA
# ─────────────────────────────────────────────
def _nueva_pagina(c, titulo_doc, numero_doc, empresa):
    c.showPage()
    return _pintar_cabecera(c, empresa, titulo_doc, numero_doc, meta_lineas=None)


# ─────────────────────────────────────────────
# CABECERA PRINCIPAL
# ─────────────────────────────────────────────
def _pintar_cabecera(c, empresa, titulo_doc, numero_doc, meta_lineas=None):
    """
    Pinta la cabecera completa y devuelve la y disponible tras ella.
    """

    nombre_emp = empresa[0]
    cif = empresa[1]

    direccion = empresa[2]
    codigo_postal = empresa[3]
    poblacion = empresa[4]
    provincia = empresa[5]
    pais = empresa[6]

    email_emp = empresa[7]
    telefono_emp = empresa[8]
    logo = empresa[9]

    direccion_emp = direccion or ""

    linea_cp = ""
    if codigo_postal or poblacion:
        linea_cp = f"{codigo_postal or ''} {poblacion or ''}".strip()

    if provincia and pais:
        linea_prov = f"{provincia} · {pais}"
    else:
        linea_prov = provincia or pais or ""

    HEADER_H = 4.8 * cm
    top_y = PAGE_H - 1.4 * cm
    bottom_y = PAGE_H - HEADER_H - 1.0 * cm

    # ─────────────────────────────────────
    # Fondo cabecera
    # ─────────────────────────────────────

    c.setFillColor(C_BG_HEADER)
    c.roundRect(MARGIN_X, bottom_y, CONTENT_W, HEADER_H, 10, fill=1, stroke=0)

    c.setFillColor(C_ACCENT)
    c.roundRect(MARGIN_X, bottom_y, 0.35 * cm, HEADER_H, 5, fill=1, stroke=0)

    # ─────────────────────────────────────
    # LOGO
    # ─────────────────────────────────────

    LOGO_ZONE_X = MARGIN_X + 0.65 * cm
    LOGO_MAX_W = 4.5 * cm
    LOGO_MAX_H = 3.2 * cm

    logo_drawn_w = 0

    if logo and os.path.exists(logo):

        lw, lh = _calc_logo_size(logo, LOGO_MAX_W, LOGO_MAX_H)

        if lw > 0 and lh > 0:

            logo_y = bottom_y + (HEADER_H - lh) / 2

            c.drawImage(
                logo,
                LOGO_ZONE_X,
                logo_y,
                width=lw,
                height=lh,
                preserveAspectRatio=True,
                mask="auto",
            )

            logo_drawn_w = lw + 0.5 * cm

    # ─────────────────────────────────────
    # DATOS EMPRESA
    # ─────────────────────────────────────

    emp_x = LOGO_ZONE_X + logo_drawn_w
    emp_y = top_y - 1.0 * cm

    # límite antes del bloque factura
    BADGE_LIMIT = PAGE_W - MARGIN_X - 6.5 * cm
    max_width = BADGE_LIMIT - emp_x

    # dividir nombre en máximo 2 líneas
    lines = _split_text(c, nombre_emp, max_width, font="Helvetica-Bold", size=13)

    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]

    if len(lines) == 1:
        _draw_text(c, emp_x, emp_y, lines[0], font="Helvetica-Bold", size=13)
        emp_y -= 0.52 * cm

    else:
        _draw_text(c, emp_x, emp_y, lines[0], font="Helvetica-Bold", size=13)
        _draw_text(
            c, emp_x, emp_y - 0.45 * cm, lines[1], font="Helvetica-Bold", size=13
        )
        emp_y -= 0.9 * cm

    for dato in filter(
        None,
        [
            f"CIF: {cif}" if cif else None,
            direccion_emp,
            linea_cp,
            linea_prov,
            f"Tel: {telefono_emp}" if telefono_emp else None,
            f"Email: {email_emp}" if email_emp else None,
        ],
    ):
        _draw_text(c, emp_x, emp_y, dato, size=8.5, color=C_TEXT_MID)
        emp_y -= 0.38 * cm

    # ─────────────────────────────────────
    # BLOQUE DOCUMENTO
    # ─────────────────────────────────────

    right_x = PAGE_W - MARGIN_X - 0.5 * cm

    badge_w = 5.8 * cm
    badge_h = 1.1 * cm

    badge_x = right_x - badge_w
    badge_y = top_y - badge_h + 0.08 * cm

    c.setFillColor(C_ACCENT)

    c.roundRect(badge_x, badge_y, badge_w, badge_h, 6, fill=1, stroke=0)

    _draw_centered(
        c,
        badge_x + badge_w / 2,
        badge_y + 0.3 * cm,
        titulo_doc,
        font="Helvetica-Bold",
        size=13,
        color=C_WHITE,
    )

    num_y = badge_y - 0.55 * cm

    _draw_right(
        c,
        right_x,
        num_y,
        numero_doc,
        font="Helvetica-Bold",
        size=11,
        color=C_ACCENT_DARK,
    )

    meta_y = num_y - 0.45 * cm

    if meta_lineas:

        for label, value in meta_lineas:

            if value:

                _draw_right(
                    c,
                    right_x,
                    meta_y,
                    f"{label}: {value}",
                    size=8.5,
                    color=C_TEXT_MID,
                )

                meta_y -= 0.38 * cm

    # ─────────────────────────────────────
    # Línea separadora
    # ─────────────────────────────────────

    sep_y = bottom_y - 0.55 * cm

    c.setStrokeColor(C_BORDER)
    c.setLineWidth(0.5)

    c.line(MARGIN_X, sep_y, PAGE_W - MARGIN_X, sep_y)

    return sep_y - 0.5 * cm


# ─────────────────────────────────────────────
# BLOQUE CLIENTE
# ─────────────────────────────────────────────
def _pintar_bloque_cliente(
    c,
    y,
    cliente,
    dni=None,
    direccion_cli=None,
    codigo_postal_cli=None,
    poblacion_cli=None,
    provincia_cli=None,
    pais_cli=None,
    email_cli=None,
    telefono_cli=None,
):

    BOX_W = 9.0 * cm
    INNER_X = MARGIN_X + 0.4 * cm

    COL2_X = INNER_X + 4.6 * cm

    # ─────────────────────────────────────
    # Construcción datos
    # ─────────────────────────────────────

    linea_cp = ""
    if codigo_postal_cli or poblacion_cli:
        linea_cp = f"{codigo_postal_cli or ''} {poblacion_cli or ''}".strip()

    linea_prov = ""
    if provincia_cli and pais_cli:
        linea_prov = f"{provincia_cli} · {pais_cli}"
    else:
        linea_prov = provincia_cli or pais_cli or ""

    # Nombre
    nombre = _safe_str(cliente)

    # Columnas
    col_izq = []
    col_der = []

    if dni:
        col_izq.append(f"DNI/NIF: {dni}")

    if direccion_cli:
        col_izq.append(direccion_cli)

    if linea_cp:
        col_izq.append(linea_cp)

    if telefono_cli:
        col_der.append(f"Tel: {telefono_cli}")

    if email_cli:
        col_der.append(email_cli)

    if linea_prov:
        col_der.append(linea_prov)

    filas = max(len(col_izq), len(col_der))

    # ─────────────────────────────────────
    # Altura caja
    # ─────────────────────────────────────

    BOX_H = 1.4 * cm + filas * 0.42 * cm

    box_y = y - BOX_H

    c.setFillColor(C_WHITE)
    c.setStrokeColor(C_BORDER)
    c.setLineWidth(0.6)

    c.roundRect(MARGIN_X, box_y, BOX_W, BOX_H, 8, fill=1, stroke=1)

    # ─────────────────────────────────────
    # Cabecera CLIENTE
    # ─────────────────────────────────────

    c.setFillColor(C_ACCENT)

    c.roundRect(
        MARGIN_X,
        box_y + BOX_H - 0.62 * cm,
        BOX_W,
        0.62 * cm,
        8,
        fill=1,
        stroke=0,
    )

    c.rect(
        MARGIN_X,
        box_y + BOX_H - 0.62 * cm,
        BOX_W,
        0.31 * cm,
        fill=1,
        stroke=0,
    )

    _draw_text(
        c,
        INNER_X,
        box_y + BOX_H - 0.44 * cm,
        "CLIENTE",
        font="Helvetica-Bold",
        size=8,
        color=C_WHITE,
    )

    # ─────────────────────────────────────
    # Nombre cliente
    # ─────────────────────────────────────

    nombre_y = box_y + BOX_H - 1.0 * cm

    _draw_text(
        c,
        INNER_X,
        nombre_y,
        nombre,
        font="Helvetica-Bold",
        size=10,
        color=C_TEXT_DARK,
    )

    # ─────────────────────────────────────
    # Datos columnas
    # ─────────────────────────────────────

    text_y = nombre_y - 0.45 * cm

    for i in range(filas):

        if i < len(col_izq):
            _draw_text(
                c,
                INNER_X,
                text_y,
                col_izq[i],
                size=8.5,
                color=C_TEXT_MID,
            )

        if i < len(col_der):
            _draw_text(
                c,
                COL2_X,
                text_y,
                col_der[i],
                size=8.5,
                color=C_TEXT_MID,
            )

        text_y -= 0.42 * cm

    return box_y - 0.7 * cm


# ─────────────────────────────────────────────
# TABLA DE LÍNEAS
# ─────────────────────────────────────────────
def _pintar_tabla_lineas(c, y, lineas, titulo_doc, numero_doc, empresa):
    HEADER_H = 0.72 * cm
    MIN_Y = 4.0 * cm  # margen inferior antes de saltar página

    def pintar_cabecera_tabla(y_local):
        # Fondo cabecera tabla
        c.setFillColor(C_TABLE_HEAD)
        c.roundRect(
            MARGIN_X, y_local - HEADER_H, CONTENT_W, HEADER_H, 5, fill=1, stroke=0
        )

        text_y = y_local - 0.46 * cm
        _draw_text(
            c,
            COL_DESC_X,
            text_y,
            "Descripción",
            font="Helvetica-Bold",
            size=9,
            color=C_WHITE,
        )
        _draw_right(
            c, COL_CANT_X, text_y, "Cant.", font="Helvetica-Bold", size=9, color=C_WHITE
        )
        _draw_right(
            c,
            COL_PRECIO_X,
            text_y,
            "Precio unit.",
            font="Helvetica-Bold",
            size=9,
            color=C_WHITE,
        )
        _draw_right(
            c, COL_IVA_X, text_y, "IVA", font="Helvetica-Bold", size=9, color=C_WHITE
        )
        _draw_right(
            c,
            COL_TOTAL_X,
            text_y,
            "Total",
            font="Helvetica-Bold",
            size=9,
            color=C_WHITE,
        )

        return y_local - HEADER_H

    y = pintar_cabecera_tabla(y)
    y -= 0.14 * cm  # gap entre cabecera y primera fila

    total_base = 0.0
    total_iva = 0.0

    for idx, (desc, cant, precio, iva, total_linea) in enumerate(lineas):
        desc_lineas = _split_text(c, str(desc), COL_DESC_W, size=9)
        if not desc_lineas:
            desc_lineas = [""]

        row_h = max(0.64 * cm, len(desc_lineas) * 0.42 * cm + 0.30 * cm)

        # ¿Salto de página?
        if y - row_h < MIN_Y:
            y = _nueva_pagina(c, titulo_doc, numero_doc, empresa)
            y = pintar_cabecera_tabla(y)

        # Fondo fila alternada
        if idx % 2 == 1:
            c.setFillColor(C_BG_ROW_ALT)
            c.rect(MARGIN_X, y - row_h, CONTENT_W, row_h, fill=1, stroke=0)

        # Línea separadora inferior de fila
        c.setStrokeColor(C_BORDER)
        c.setLineWidth(0.3)
        c.line(MARGIN_X, y - row_h, PAGE_W - MARGIN_X, y - row_h)

        base = float(cant) * float(precio)
        iva_import = float(total_linea) - base
        total_base += base
        total_iva += iva_import

        # Centrado vertical unificado: descripción y numéricos alineados
        PADDING_V = 0.15 * cm  # padding interno arriba y abajo
        total_desc_h = len(desc_lineas) * 0.42 * cm
        desc_start_y = (
            y - PADDING_V - 0.30 * cm
        )  # arranca con padding desde el borde superior

        text_y = desc_start_y
        for linea_desc in desc_lineas:
            _draw_text(c, COL_DESC_X, text_y, linea_desc, size=9, color=C_TEXT_DARK)
            text_y -= 0.42 * cm

        mid_y = y - (row_h / 2) - 0.10 * cm  # centrado vertical de numéricos
        _draw_right(
            c, COL_CANT_X, mid_y, _fmt_cantidad(cant), size=9, color=C_TEXT_DARK
        )
        _draw_right(
            c,
            COL_PRECIO_X,
            mid_y,
            f"{float(precio):.2f} \u20ac",
            size=9,
            color=C_TEXT_DARK,
        )
        _draw_right(c, COL_IVA_X, mid_y, f"{float(iva):.0f}%", size=9, color=C_TEXT_MID)
        _draw_right(
            c,
            COL_TOTAL_X,
            mid_y,
            f"{float(total_linea):.2f} \u20ac",
            size=9,
            color=C_TEXT_DARK,
            font="Helvetica-Bold",
        )

        y -= row_h

    # Línea cierre tabla
    c.setStrokeColor(C_ACCENT)
    c.setLineWidth(1.0)
    c.line(MARGIN_X, y, PAGE_W - MARGIN_X, y)

    return y, total_base, total_iva


# ─────────────────────────────────────────────
# CAJA TOTALES
# ─────────────────────────────────────────────
def _pintar_totales(c, y, total_base, total_iva, total):
    BOX_W = 7.2 * cm
    ROWS = [
        ("Base imponible", f"{total_base:.2f} \u20ac", False),
        ("IVA", f"{total_iva:.2f} \u20ac", False),
        ("TOTAL", f"{float(total):.2f} \u20ac", True),
    ]
    ROW_H = 0.68 * cm
    BOX_H = ROW_H * len(ROWS)
    box_x = PAGE_W - MARGIN_X - BOX_W
    box_y = y - BOX_H - 0.4 * cm

    # Sombra suave
    c.setFillColor(colors.HexColor("#E2E8F0"))
    c.roundRect(box_x + 0.1 * cm, box_y - 0.1 * cm, BOX_W, BOX_H, 8, fill=1, stroke=0)

    c.setFillColor(C_WHITE)
    c.setStrokeColor(C_BORDER)
    c.setLineWidth(0.6)
    c.roundRect(box_x, box_y, BOX_W, BOX_H, 8, fill=1, stroke=1)

    for i, (label, value, is_total) in enumerate(ROWS):
        row_y = box_y + BOX_H - (i + 1) * ROW_H

        if is_total:
            c.setFillColor(C_ACCENT)
            c.roundRect(box_x, row_y, BOX_W, ROW_H, 8, fill=1, stroke=0)
            # Esquinas superiores rectas para la última fila
            c.rect(box_x, row_y + ROW_H * 0.5, BOX_W, ROW_H * 0.5, fill=1, stroke=0)

        text_y = row_y + (ROW_H - 0.28 * cm) / 2
        lbl_col = C_WHITE if is_total else C_TEXT_MID
        val_col = C_WHITE if is_total else C_TEXT_DARK
        lbl_font = "Helvetica-Bold" if is_total else "Helvetica"
        val_font = "Helvetica-Bold"
        lbl_size = 10 if is_total else 9
        val_size = 11 if is_total else 9

        _draw_text(
            c,
            box_x + 0.45 * cm,
            text_y,
            label,
            font=lbl_font,
            size=lbl_size,
            color=lbl_col,
        )
        _draw_right(
            c,
            box_x + BOX_W - 0.45 * cm,
            text_y,
            value,
            font=val_font,
            size=val_size,
            color=val_col,
        )

        # Separador entre filas (excepto último)
        if not is_total and i < len(ROWS) - 1:
            c.setStrokeColor(C_BORDER)
            c.setLineWidth(0.3)
            c.line(box_x + 0.3 * cm, row_y, box_x + BOX_W - 0.3 * cm, row_y)

    return box_y - 0.5 * cm


# ─────────────────────────────────────────────
# PIE DE PÁGINA
# ─────────────────────────────────────────────
def _pintar_pie(c, texto_1, texto_2=None):
    pie_y = 1.6 * cm
    c.setStrokeColor(C_BORDER)
    c.setLineWidth(0.4)
    c.line(MARGIN_X, pie_y + 0.3 * cm, PAGE_W - MARGIN_X, pie_y + 0.3 * cm)

    _draw_text(c, MARGIN_X, pie_y, texto_1, size=7.5, color=C_TEXT_LIGHT)
    if texto_2:
        _draw_text(c, MARGIN_X, pie_y - 0.35 * cm, texto_2, size=7, color=C_TEXT_LIGHT)

    pagina = c.getPageNumber()

    _draw_right(
        c,
        PAGE_W - MARGIN_X,
        pie_y,
        f"Pág. {pagina}",
        size=7.5,
        color=C_TEXT_LIGHT,
    )


# ─────────────────────────────────────────────
# PDF FACTURA
# ─────────────────────────────────────────────
def generar_pdf_factura(factura_id):
    logging.info(f"[PDF] Generar factura: id={factura_id}")
    conn = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        empresa = obtener_empresa()

        if not empresa:
            conn.close()
            logging.warning("[PDF] Empresa no configurada.")
            return None

        _aplicar_color_empresa(empresa)

        # =================================================
        # DATOS EMPRESA
        # =================================================

        (
            nombre_emp,
            cif_emp,
            direccion_emp,
            codigo_postal_emp,
            poblacion_emp,
            provincia_emp,
            pais_emp,
            email_emp,
            telefono_emp,
            logo_emp,
            iban_empresa,
            creditor_id,
            bic_empresa,
            color_factura,
        ) = empresa[:14]

        # Formatear IBAN bonito
        def formatear_iban(iban):
            if not iban:
                return ""
            iban = iban.replace(" ", "")
            return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))

        # =================================================
        # OBTENER FACTURA
        # =================================================

        cursor.execute(
            """
            SELECT
                d.numero_legal, d.fecha, d.fecha_vencimiento,
                d.estado, d.forma_pago, d.fecha_pago, d.total,
                d.factura_rectificada_id, d.motivo_rectificacion,
                c.nombre, c.dni, c.direccion,
                c.codigo_postal, c.poblacion, c.provincia, c.pais,
                c.email, c.telefono
            FROM documentos d
            JOIN clientes c ON c.id = d.cliente_id
            WHERE d.id = ? AND d.tipo = 'FACTURA'
            """,
            (factura_id,),
        )

        factura = cursor.fetchone()

        if not factura:
            conn.close()
            logging.warning(f"[PDF] Factura no encontrada: id={factura_id}")
            return None

        (
            numero_legal,
            fecha_sql,
            fecha_venc_sql,
            estado,
            forma_pago,
            fecha_pago_sql,
            total,
            factura_rectificada_id,
            motivo_rectificacion,
            cliente,
            dni,
            direccion_cli,
            codigo_postal_cli,
            poblacion_cli,
            provincia_cli,
            pais_cli,
            email_cli,
            telefono_cli,
        ) = factura

        fecha = _fmt_fecha_es(fecha_sql)
        vencimiento = _fmt_fecha_es(fecha_venc_sql) if fecha_venc_sql else fecha
        fecha_pago = _fmt_fecha_es(fecha_pago_sql) if fecha_pago_sql else None
        forma_pago = forma_pago or "CONTADO"
        es_rect = factura_rectificada_id is not None

        rectifica_numero = None

        if es_rect:
            cursor.execute(
                "SELECT numero_legal FROM documentos WHERE id = ?",
                (factura_rectificada_id,),
            )
            row = cursor.fetchone()
            rectifica_numero = row[0] if row else None

        # =================================================
        # OBTENER LINEAS
        # =================================================

        cursor.execute(
            """
            SELECT descripcion, cantidad, precio, iva, total
            FROM documento_lineas
            WHERE documento_id = ?
            ORDER BY id ASC
            """,
            (factura_id,),
        )

        lineas = cursor.fetchall()

        conn.close()

        # =================================================
        # CREAR PDF
        # =================================================

        ruta_salida = BASE_DIR / "facturas_pdf"
        archivo = ruta_salida / f"{numero_legal}.pdf"

        c = _crear_canvas_pdf(archivo)

        titulo = "FACTURA RECTIFICATIVA" if es_rect else "FACTURA"

        meta_lineas = [
            ("Fecha", fecha),
            ("Vencimiento", vencimiento),
            ("Forma de pago", forma_pago),
            ("Estado", estado),
        ]

        if es_rect and rectifica_numero:
            meta_lineas.append(("Rectifica a", rectifica_numero))

        if es_rect and motivo_rectificacion:
            meta_lineas.append(("Motivo", motivo_rectificacion))

        # =================================================
        # CABECERA
        # =================================================

        y = _pintar_cabecera(c, empresa, titulo, numero_legal, meta_lineas)

        # =================================================
        # BLOQUE CLIENTE
        # =================================================

        y = _pintar_bloque_cliente(
            c,
            y,
            cliente,
            dni=dni,
            direccion_cli=direccion_cli,
            codigo_postal_cli=codigo_postal_cli,
            poblacion_cli=poblacion_cli,
            provincia_cli=provincia_cli,
            pais_cli=pais_cli,
            email_cli=email_cli,
            telefono_cli=telefono_cli,
        )

        y -= 0.4 * cm

        # =================================================
        # TABLA LINEAS
        # =================================================

        y, total_base, total_iva = _pintar_tabla_lineas(
            c,
            y,
            lineas,
            titulo,
            numero_legal,
            empresa,
        )

        _pintar_totales(c, y, total_base, total_iva, total)

        # =================================================
        # ESTADO FACTURA
        # =================================================

        if estado == "PAGADA" and fecha_pago:
            texto_estado = f"Factura pagada el {fecha_pago}."
        elif estado == "VENCIDA":
            texto_estado = "Factura vencida pendiente de pago."
        else:
            texto_estado = "Factura pendiente de pago."

        texto_pago = f"Forma de pago: {forma_pago}"

        if forma_pago and "transfer" in forma_pago.lower() and iban_empresa:
            texto_pago += f"  ·  IBAN: {formatear_iban(iban_empresa)}"

            if bic_empresa:
                texto_pago += f"  ·  BIC: {bic_empresa}"

        _pintar_pie(
            c,
            f"{texto_pago}  ·  {texto_estado}",
            "Documento generado electrónicamente. Preparado para sistemas de facturación electrónica.",
        )

        c.save()

        logging.info(f"[PDF] Factura generada OK: {archivo}")

        return str(archivo)

    except Exception:

        logging.exception(f"[PDF] Error generando factura id={factura_id}")

        if conn:
            try:
                conn.close()
            except Exception:
                pass

        return None


# ─────────────────────────────────────────────
# PDF ALBARÁN
# ─────────────────────────────────────────────
def generar_pdf_albaran(albaran_id):

    logging.info(f"[PDF] Generar albarán: id={albaran_id}")
    conn = None

    try:

        conn = get_connection()
        cursor = conn.cursor()

        empresa = obtener_empresa()

        if not empresa:
            conn.close()
            logging.warning("[PDF] Empresa no configurada.")
            return None

        _aplicar_color_empresa(empresa)

        cursor.execute(
            """
            SELECT
                d.numero,
                d.fecha,
                d.total,
                c.nombre,
                c.dni,
                c.direccion,
                c.codigo_postal,
                c.poblacion,
                c.provincia,
                c.pais,
                c.email,
                c.telefono
            FROM documentos d
            JOIN clientes c ON c.id = d.cliente_id
            WHERE d.id = ? AND d.tipo = 'ALBARAN'
            """,
            (albaran_id,),
        )

        alb = cursor.fetchone()

        if not alb:
            conn.close()
            logging.warning(f"[PDF] Albarán no encontrado: id={albaran_id}")
            return None

        (
            numero,
            fecha_sql,
            total,
            cliente,
            dni,
            direccion_cli,
            codigo_postal_cli,
            poblacion_cli,
            provincia_cli,
            pais_cli,
            email_cli,
            telefono_cli,
        ) = alb

        fecha = _fmt_fecha_es(fecha_sql)

        cursor.execute(
            """
            SELECT descripcion, cantidad, precio, iva, total
            FROM documento_lineas
            WHERE documento_id = ?
            ORDER BY id ASC
            """,
            (albaran_id,),
        )

        lineas = cursor.fetchall()

        conn.close()

        ruta_salida = BASE_DIR / "albaranes_pdf"
        archivo = ruta_salida / f"{numero}.pdf"

        c = _crear_canvas_pdf(archivo)

        meta_lineas = [
            ("Fecha", fecha),
        ]

        y = _pintar_cabecera(
            c,
            empresa,
            "ALBARÁN",
            numero,
            meta_lineas,
        )

        y = _pintar_bloque_cliente(
            c,
            y,
            cliente,
            dni=dni,
            direccion_cli=direccion_cli,
            codigo_postal_cli=codigo_postal_cli,
            poblacion_cli=poblacion_cli,
            provincia_cli=provincia_cli,
            pais_cli=pais_cli,
            email_cli=email_cli,
            telefono_cli=telefono_cli,
        )

        y -= 0.4 * cm

        y, total_base, total_iva = _pintar_tabla_lineas(
            c,
            y,
            lineas,
            "ALBARÁN",
            numero,
            empresa,
        )

        _pintar_totales(c, y, total_base, total_iva, total)

        _pintar_pie(
            c,
            "Albarán de entrega. Este documento no es una factura.",
            "Documento generado desde el programa de facturación.",
        )

        c.save()

        logging.info(f"[PDF] Albarán generado OK: {archivo}")

        return str(archivo)

    except Exception:

        logging.exception(f"[PDF] Error generando albarán id={albaran_id}")

        if conn:
            try:
                conn.close()
            except Exception:
                pass

        return None
