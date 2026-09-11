from app.database.db import get_connection


def crear_tablas():
    conn = get_connection()
    cursor = conn.cursor()

    # ==================================================
    # CLIENTES (VENTAS)
    # ==================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            email TEXT,
            telefono TEXT,
            direccion TEXT,
            codigo_postal TEXT,
            poblacion TEXT,
            provincia TEXT,
            pais TEXT,
            dni TEXT,
            iban TEXT,
            mandato_sepa TEXT,
            fecha_mandato TEXT,
            activo INTEGER DEFAULT 1
        )
        """
    )

    # ==================================================
    # PROVEEDORES (COMPRAS)
    # ==================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cif TEXT,
            email TEXT,
            telefono TEXT,
            direccion TEXT,
            codigo_postal TEXT,
            poblacion TEXT,
            provincia TEXT,
            pais TEXT,
            iban TEXT,
            activo INTEGER DEFAULT 1
        )
        """
    )

    # ==================================================
    # PRODUCTOS (CON REFERENCIA + EAN + STOCK)
    # ==================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referencia TEXT,
            ean TEXT,
            nombre TEXT NOT NULL,
            precio REAL NOT NULL,
            iva REAL NOT NULL DEFAULT 21,
            stock REAL DEFAULT 0,
            control_stock INTEGER DEFAULT 1,
            activo INTEGER DEFAULT 1
        )
        """
    )

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_productos_referencia
        ON productos (referencia)
        """
    )

    # ==================================================
    # MOVIMIENTOS DE STOCK
    # ==================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS movimientos_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            cantidad REAL NOT NULL,
            fecha TEXT NOT NULL,
            documento_id INTEGER,
            detalle TEXT,
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )
        """
    )

    # ==================================================
    # DOCUMENTOS (VENTAS)
    # ==================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT CHECK(tipo IN ('ALBARAN', 'FACTURA')) NOT NULL,
            numero TEXT NOT NULL,
            numero_legal TEXT UNIQUE,
            fecha TEXT NOT NULL,
            cliente_id INTEGER NOT NULL,
            total REAL NOT NULL DEFAULT 0,

            bloqueada INTEGER DEFAULT 0,

            estado TEXT DEFAULT 'PENDIENTE',
            fecha_vencimiento TEXT,
            forma_pago TEXT,
            dia_pago INTEGER,
            fecha_pago TEXT,

            tipo_vencimiento TEXT,
            iban TEXT,
            estado_cobro TEXT DEFAULT 'PENDIENTE',

            factura_rectificada_id INTEGER,
            motivo_rectificacion TEXT,

            hash TEXT,
            enviado_verifactu INTEGER DEFAULT 0,

            creado_en TEXT,

            FOREIGN KEY (cliente_id) REFERENCES clientes(id),
            FOREIGN KEY (factura_rectificada_id) REFERENCES documentos(id)
        )
        """
    )

    # Índices útiles para documentos
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_documentos_cliente
        ON documentos (cliente_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_documentos_estado
        ON documentos (estado)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_documentos_forma_pago
        ON documentos (forma_pago)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_documentos_estado_cobro
        ON documentos (estado_cobro)
        """
    )

    # ==================================================
    # LÍNEAS DOCUMENTOS (VENTAS)
    # ==================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS documento_lineas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_id INTEGER NOT NULL,
            producto_id INTEGER,
            descripcion TEXT,
            cantidad REAL,
            precio REAL,
            iva REAL,
            total REAL,
            FOREIGN KEY (documento_id) REFERENCES documentos(id),
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )
        """
    )

    # ==================================================
    # DOCUMENTOS COMPRAS
    # ==================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS documentos_compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor_id INTEGER NOT NULL,
            numero_factura TEXT NOT NULL,
            fecha TEXT NOT NULL,
            fecha_vencimiento TEXT,
            total REAL NOT NULL DEFAULT 0,

            estado_pago TEXT DEFAULT 'PENDIENTE',
            forma_pago TEXT,
            fecha_pago TEXT,

            creado_en TEXT,
            FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
        )
        """
    )

    # ==================================================
    # LÍNEAS DOCUMENTOS COMPRAS
    # ==================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS documento_compras_lineas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_compra_id INTEGER NOT NULL,
            producto_id INTEGER,
            descripcion TEXT,
            cantidad REAL,
            precio REAL,
            iva REAL,
            total REAL,
            FOREIGN KEY (documento_compra_id) REFERENCES documentos_compras(id),
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )
        """
    )

    # ==================================================
    # NUMERACIÓN LEGAL
    # ==================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS numeracion (
            tipo TEXT NOT NULL,
            año INTEGER NOT NULL,
            ultimo INTEGER NOT NULL,
            PRIMARY KEY (tipo, año)
        )
        """
    )

    # ==================================================
    # EVENTOS DOCUMENTOS
    # ==================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS eventos_documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_id INTEGER NOT NULL,
            tipo_documento TEXT NOT NULL,
            evento TEXT NOT NULL,
            fecha TEXT NOT NULL,
            detalle TEXT,
            FOREIGN KEY (documento_id) REFERENCES documentos(id)
        )
        """
    )

    # ==================================================
    # REMESAS SEPA
    # ==================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS remesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_remesa TEXT,
            fecha TEXT NOT NULL,
            total REAL NOT NULL DEFAULT 0,
            estado TEXT DEFAULT 'GENERADA',
            archivo_xml TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS remesa_lineas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            remesa_id INTEGER NOT NULL,
            factura_id INTEGER NOT NULL,
            importe REAL NOT NULL,
            FOREIGN KEY (remesa_id) REFERENCES remesas(id),
            FOREIGN KEY (factura_id) REFERENCES documentos(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_remesa_lineas_remesa
        ON remesa_lineas (remesa_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_remesa_lineas_factura
        ON remesa_lineas (factura_id)
        """
    )

    # ==================================================
    # EMPRESA
    # ==================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS empresa (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            cif TEXT,
            direccion TEXT,
            codigo_postal TEXT,
            poblacion TEXT,
            provincia TEXT,
            pais TEXT,
            email TEXT,
            telefono TEXT,
            logo TEXT,
            iban_empresa TEXT,
            creditor_id TEXT,
            bic TEXT,
            color_factura TEXT,
            smtp_server TEXT,
            smtp_port INTEGER,
            smtp_user TEXT,
            smtp_password TEXT,
            smtp_security TEXT
        )
        """
    )

    # ==================================================
    # MIGRACIONES SEGURAS (BASES ANTIGUAS)
    # ==================================================

    # Productos
    _add_column_if_not_exists(cursor, "productos", "referencia", "TEXT")
    _add_column_if_not_exists(cursor, "productos", "ean", "TEXT")
    _add_column_if_not_exists(cursor, "productos", "stock", "REAL DEFAULT 0")
    _add_column_if_not_exists(cursor, "productos", "control_stock", "INTEGER DEFAULT 1")
    _add_column_if_not_exists(cursor, "productos", "activo", "INTEGER DEFAULT 1")

    # Documento líneas (ventas)
    _add_column_if_not_exists(cursor, "documento_lineas", "producto_id", "INTEGER")

    # Documento líneas compras
    _add_column_if_not_exists(
        cursor, "documento_compras_lineas", "producto_id", "INTEGER"
    )

    # Clientes / Proveedores
    _add_column_if_not_exists(cursor, "proveedores", "activo", "INTEGER DEFAULT 1")
    _add_column_if_not_exists(cursor, "clientes", "activo", "INTEGER DEFAULT 1")
    _add_column_if_not_exists(cursor, "clientes", "iban", "TEXT")
    _add_column_if_not_exists(cursor, "clientes", "mandato_sepa", "TEXT")
    _add_column_if_not_exists(cursor, "clientes", "fecha_mandato", "TEXT")

    # Direcciones completas
    _add_column_if_not_exists(cursor, "clientes", "codigo_postal", "TEXT")
    _add_column_if_not_exists(cursor, "clientes", "poblacion", "TEXT")
    _add_column_if_not_exists(cursor, "clientes", "provincia", "TEXT")
    _add_column_if_not_exists(cursor, "clientes", "pais", "TEXT")

    _add_column_if_not_exists(cursor, "proveedores", "codigo_postal", "TEXT")
    _add_column_if_not_exists(cursor, "proveedores", "poblacion", "TEXT")
    _add_column_if_not_exists(cursor, "proveedores", "provincia", "TEXT")
    _add_column_if_not_exists(cursor, "proveedores", "pais", "TEXT")

    _add_column_if_not_exists(cursor, "empresa", "codigo_postal", "TEXT")
    _add_column_if_not_exists(cursor, "empresa", "poblacion", "TEXT")
    _add_column_if_not_exists(cursor, "empresa", "provincia", "TEXT")
    _add_column_if_not_exists(cursor, "empresa", "pais", "TEXT")

    # Empresa
    _add_column_if_not_exists(cursor, "empresa", "logo", "TEXT")
    _add_column_if_not_exists(cursor, "empresa", "iban_empresa", "TEXT")
    _add_column_if_not_exists(cursor, "empresa", "creditor_id", "TEXT")
    _add_column_if_not_exists(cursor, "empresa", "bic", "TEXT")
    _add_column_if_not_exists(cursor, "empresa", "color_factura", "TEXT")

    # SMTP
    _add_column_if_not_exists(cursor, "empresa", "smtp_server", "TEXT")
    _add_column_if_not_exists(cursor, "empresa", "smtp_port", "INTEGER")
    _add_column_if_not_exists(cursor, "empresa", "smtp_user", "TEXT")
    _add_column_if_not_exists(cursor, "empresa", "smtp_password", "TEXT")
    _add_column_if_not_exists(cursor, "empresa", "smtp_security", "TEXT")

    # Documentos
    _add_column_if_not_exists(cursor, "documentos", "numero_legal", "TEXT")
    _add_column_if_not_exists(cursor, "documentos", "fecha_pago", "TEXT")
    _add_column_if_not_exists(cursor, "documentos", "tipo_vencimiento", "TEXT")
    _add_column_if_not_exists(cursor, "documentos", "iban", "TEXT")
    _add_column_if_not_exists(
        cursor, "documentos", "estado_cobro", "TEXT DEFAULT 'PENDIENTE'"
    )
    _add_column_if_not_exists(cursor, "documentos", "factura_rectificada_id", "INTEGER")
    _add_column_if_not_exists(cursor, "documentos", "motivo_rectificacion", "TEXT")
    _add_column_if_not_exists(cursor, "documentos", "hash", "TEXT")
    _add_column_if_not_exists(
        cursor, "documentos", "enviado_verifactu", "INTEGER DEFAULT 0"
    )
    _add_column_if_not_exists(cursor, "documentos", "bloqueada", "INTEGER DEFAULT 0")
    _add_column_if_not_exists(cursor, "documentos", "dia_pago", "INTEGER")

    # Remesas
    _add_column_if_not_exists(cursor, "remesas", "codigo_remesa", "TEXT")

    conn.commit()
    conn.close()


# ==================================================
# HELPER MIGRACIÓN SEGURA
# ==================================================
def _add_column_if_not_exists(cursor, table, column, definition):
    cursor.execute(f"PRAGMA table_info({table})")
    columnas = [fila[1] for fila in cursor.fetchall()]

    if column not in columnas:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
