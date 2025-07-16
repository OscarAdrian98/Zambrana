from flask import Flask, render_template, request, jsonify
from scraping_url import scrapear_producto
from ia import (
    generar_reseñas_groq,
    generar_descripcion_larga_groq,
    generar_meta_title_groq,
    generar_meta_description_groq,
    generar_descripcion_larga_desde_existente_groq
)
import logging
import sys
from db.conexion import basedatos_seo, basedatos_prestashop
from datetime import datetime

# Configuración del logger global
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

file_handler = logging.FileHandler('flask_error.log', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)

if logger.hasHandlers():
    logger.handlers.clear()

logger.addHandler(file_handler)
logger.addHandler(console_handler)

app = Flask(__name__)


@app.errorhandler(Exception)
def handle_exception(e):
    logging.exception("🔴 Error no controlado en Flask:")
    return jsonify({"success": False, "error": "Error interno en el servidor."}), 500


@app.route("/", methods=["GET", "POST"])
def index():
    datos = None
    if request.method == "POST":
        url = request.form.get("url_producto")
        if url:
            (
                id_product,
                nombre_producto,
                _,
                descripcion_larga,
                imagen_url,
                meta_title,
                meta_description,
            ) = scrapear_producto(url)

            conn = basedatos_seo()
            ya_existe_en_seo = False
            try:
                with conn.cursor() as cursor:
                    sql_check = """
                        SELECT COUNT(*) as total
                        FROM productos
                        WHERE id_product = %s
                    """
                    cursor.execute(sql_check, (id_product,))
                    row = cursor.fetchone()
                    if row["total"] > 0:
                        ya_existe_en_seo = True
            finally:
                conn.close()

            datos = {
                "id_product": id_product,
                "nombre_producto": nombre_producto,
                "img_url": imagen_url,
                "descripcion_larga": descripcion_larga,
                "meta_title": meta_title or "",
                "meta_description": meta_description or "",
                "ya_existe_en_seo": ya_existe_en_seo,
            }

    return render_template("index.html", datos=datos)


@app.route("/generar_descripcion_larga", methods=["POST"])
def generar_descripcion_larga():
    data = request.json
    nombre_producto = data.get("nombre_producto")
    if not nombre_producto:
        return jsonify({"error": "Falta nombre_producto"}), 400

    texto = generar_descripcion_larga_groq(nombre_producto)
    return jsonify({
        "descripcion_larga": texto,
        "success": True
    })


@app.route("/generar_meta_title", methods=["POST"])
def generar_meta_title():
    data = request.json
    nombre_producto = data.get("nombre_producto")
    descripcion_larga = data.get("descripcion_larga", "")

    if not nombre_producto:
        return jsonify({"error": "Falta nombre_producto"}), 400

    texto = generar_meta_title_groq(nombre_producto, descripcion_larga)

    # ✅ Quitar comillas dobles
    texto = texto.replace('"', '')

    return jsonify({
        "meta_title": texto,
        "success": True
    })


@app.route("/generar_meta_description", methods=["POST"])
def generar_meta_description():
    data = request.json
    nombre_producto = data.get("nombre_producto")
    descripcion_larga = data.get("descripcion_larga", "")

    if not nombre_producto:
        return jsonify({"error": "Falta nombre_producto"}), 400

    texto = generar_meta_description_groq(nombre_producto, descripcion_larga)

    # ✅ Quitar comillas dobles
    texto = texto.replace('"', '')

    return jsonify({
        "meta_description": texto,
        "success": True
    })


@app.route("/generar_reseñas", methods=["POST"])
def generar_reseñas():
    data = request.json
    id_product = data.get("id_product")
    nombre_producto = data.get("nombre_producto")
    descripcion_larga = data.get("descripcion_larga") or ""

    if not id_product or not nombre_producto:
        return jsonify({"error": "Datos incompletos."}), 400

    try:
        conn = basedatos_seo()
        reseñas = generar_y_validar_reseñas(nombre_producto, descripcion_larga, conn)
        conn.close()

        return jsonify({
            "success": True,
            "reseñas": reseñas
        })

    except Exception as e:
        logging.exception("Error llamando a Groq:")
        return jsonify({"error": "Error al generar reseñas."}), 500


@app.route("/guardar_datos_seo", methods=["POST"])
def guardar_datos_seo_route():
    data = request.get_json()

    id_product = data.get("id_product")
    nombre_producto = data.get("nombre_producto")
    img_url = data.get("img_url")
    descripcion_larga = data.get("descripcion_larga")
    meta_title = data.get("meta_title")
    meta_description = data.get("meta_description")
    reseñas = data.get("reseñas", [])

    if not id_product or not nombre_producto:
        return jsonify({"success": False, "error": "Faltan datos obligatorios."}), 400

    try:
        se_inserto, reseñas_finales = guardar_datos_en_seo(
            id_product=id_product,
            nombre_producto=nombre_producto,
            img_url=img_url,
            descripcion_larga=descripcion_larga,
            meta_title=meta_title,
            meta_description=meta_description,
            reseñas=reseñas
        )

        if se_inserto:
            guardar_datos_en_prestashop(
                id_product=id_product,
                nombre_producto=nombre_producto,
                descripcion_larga=descripcion_larga,
                meta_title=meta_title,
                meta_description=meta_description,
                reseñas=reseñas_finales
            )
            return jsonify({"success": True})
        else:
            return jsonify({
                "success": False,
                "error": f"Producto {id_product} ya existe en la base de datos. No se guardaron datos."
            }), 200

    except Exception as e:
        logging.exception("Error guardando datos SEO o en PrestaShop:")
        return jsonify({"success": False, "error": "Error interno al guardar datos"}), 500


def guardar_datos_en_seo(id_product, nombre_producto, img_url,
                         descripcion_larga, meta_title, meta_description, reseñas=None):
    reseñas = reseñas or []
    conn = basedatos_seo()
    try:
        with conn.cursor() as cursor:
            sql_check_product = "SELECT COUNT(*) as total FROM productos WHERE id_product = %s"
            cursor.execute(sql_check_product, (id_product,))
            existe = cursor.fetchone()

            if existe["total"] > 0:
                logging.info(f"ℹ Producto {id_product} YA existe en seo_scraping. No se insertan datos adicionales.")
                return False, []

            sql_insert_product = """
                INSERT INTO productos (id_product, nombre_producto, img_url, fecha_creacion)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(sql_insert_product, (id_product, nombre_producto, img_url, datetime.now()))
            logging.info(f"✅ Insertado producto {id_product}")

            for tipo, texto in [
                ("larga", descripcion_larga),
                ("meta_title", meta_title),
                ("meta_description", meta_description)
            ]:
                if texto:
                    sql_check_desc = """
                        SELECT COUNT(*) as total
                        FROM descripciones
                        WHERE id_product = %s AND tipo = %s AND texto = %s
                    """
                    cursor.execute(sql_check_desc, (id_product, tipo, texto))
                    existe_desc = cursor.fetchone()
                    if existe_desc["total"] == 0:
                        sql_insert_desc = """
                            INSERT INTO descripciones (id_product, tipo, texto, fecha_creacion)
                            VALUES (%s, %s, %s, %s)
                        """
                        cursor.execute(sql_insert_desc, (id_product, tipo, texto, datetime.now()))
                        logging.info(f"✅ Insertada descripción {tipo}")
                    else:
                        logging.info(f"ℹ Descripción {tipo} ya existe. No se vuelve a insertar.")

            if reseñas:
                es_valido = validar_reseñas_antes_de_insertar(reseñas, conn)
                if not es_valido:
                    logging.warning("🔄 Generando reseñas nuevas con IA por duplicados encontrados...")
                    reseñas = generar_y_validar_reseñas(nombre_producto, descripcion_larga, conn)

            reseñas_insertadas = []
            if reseñas:
                for review in reseñas:
                    sql_insert_review = """
                        INSERT INTO reseñas
                        (id_product, titulo, autor, estrellas, texto, fecha_creacion)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(sql_insert_review, (
                        id_product,
                        review.get("titulo"),
                        review.get("autor"),
                        int(round(float(review.get("estrellas", 0)))),
                        review.get("texto"),
                        datetime.now(),
                    ))
                    logging.info(f"✅ Insertada reseña de autor {review.get('autor')}")
                    reseñas_insertadas.append(review)
            else:
                logging.warning("⚠️ No se insertaron reseñas (duplicadas o inexistentes).")

        conn.commit()
        logging.info(f"✅ Datos SEO guardados correctamente para producto {id_product}")
        return True, reseñas_insertadas

    except Exception as e:
        conn.rollback()
        logging.exception("❌ Error al guardar datos en la base de datos seo_scraping:", e)
        raise
    finally:
        conn.close()


def guardar_datos_en_prestashop(id_product, nombre_producto,
                                descripcion_larga, meta_title,
                                meta_description, reseñas=None):
    conn = basedatos_prestashop()
    try:
        with conn.cursor() as cursor:
            id_lang = 1

            sql_check = """
                SELECT COUNT(*) as total
                FROM ps_product_lang
                WHERE id_product = %s AND id_lang = %s
            """
            cursor.execute(sql_check, (id_product, id_lang))
            row = cursor.fetchone()

            desc_larga_html = descripcion_larga if descripcion_larga else None

            if row["total"] > 0:
                sql_update = """
                    UPDATE ps_product_lang
                    SET description = %s,
                        meta_title = %s,
                        meta_description = %s
                    WHERE id_product = %s AND id_lang = %s
                """
                cursor.execute(sql_update, (desc_larga_html, meta_title, meta_description, id_product, id_lang))
                logging.info(f"✅ Producto {id_product} actualizado en PrestaShop.")
            else:
                sql_insert = """
                    INSERT INTO ps_product_lang
                        (id_product, id_lang, name, description, meta_title, meta_description)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql_insert, (
                    id_product,
                    id_lang,
                    nombre_producto,
                    desc_larga_html,
                    meta_title,
                    meta_description
                ))
                logging.info(f"✅ Producto {id_product} insertado en PrestaShop.")

            sql_delete_reviews = """
                DELETE FROM ps_iqitreviews_products
                WHERE id_product = %s
            """
            cursor.execute(sql_delete_reviews, (id_product,))
            logging.info(f"🗑️ Reseñas anteriores borradas para producto {id_product} en PrestaShop.")

            if reseñas is None:
                reseñas = obtener_reseñas_seo(id_product)

            for review in reseñas:
                sql_insert_review = """
                    INSERT INTO ps_iqitreviews_products
                    (id_product, id_customer, id_guest, customer_name, title, comment, rating, status, date_add)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """
                cursor.execute(sql_insert_review, (
                    id_product,
                    0,
                    0,
                    review.get("autor"),
                    review.get("titulo"),
                    review.get("texto"),
                    int(round(float(review.get("estrellas", 0)))),
                    1
                ))
                logging.info(f"✅ Insertada reseña en PrestaShop de autor {review.get('autor')}")

        conn.commit()
        logging.info(f"✅ Datos guardados en PrestaShop correctamente para producto {id_product}")

    except Exception as e:
        conn.rollback()
        logging.exception("❌ Error al guardar datos en PrestaShop:", e)
        raise

    finally:
        conn.close()


@app.route("/producto/<id_product>/reseñas", methods=["GET"])
def obtener_reseñas_producto(id_product):
    try:
        reseñas = obtener_reseñas_seo(id_product)
        return jsonify({"success": True, "reseñas": reseñas})
    except Exception as e:
        logging.exception("Error obteniendo reseñas:")
        return jsonify({"success": False, "error": "Error interno obteniendo reseñas."}), 500


def obtener_reseñas_seo(id_product):
    conn = basedatos_seo()
    reseñas = []
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT titulo, autor, estrellas, texto
                FROM reseñas
                WHERE id_product = %s
            """
            cursor.execute(sql, (id_product,))
            reseñas = cursor.fetchall()
    finally:
        conn.close()

    return reseñas


def generar_y_validar_reseñas(nombre_producto, descripcion_larga, conn):
    max_intentos = 5
    intento = 0

    while intento < max_intentos:
        intento += 1
        logging.info(f"🔄 Intento de generación de reseñas #{intento}")

        reseñas = generar_reseñas_groq(nombre_producto, descripcion_larga, conn)

        if not reseñas:
            logging.warning("⚠️ No se recibieron reseñas. Reintentando...")
            continue

        repetidas = False

        with conn.cursor() as cursor:
            for review in reseñas:
                autor = review.get("autor")
                texto = review.get("texto")

                sql_check_reseña = """
                    SELECT COUNT(*) as total
                    FROM reseñas
                    WHERE autor = %s OR texto = %s
                """
                cursor.execute(sql_check_reseña, (autor, texto))
                existe_reseña = cursor.fetchone()

                if existe_reseña["total"] > 0:
                    logging.warning(f"❌ Reseña duplicada encontrada: autor={autor} o texto repetido.")
                    repetidas = True
                    break

        if repetidas:
            continue

        logging.info(f"✅ Reseñas generadas en el intento #{intento}")
        return reseñas

    logging.warning("⚠️ No se logró generar un lote único tras varios intentos.")
    return []


@app.route("/generar_descripcion_larga_desde_existente", methods=["POST"])
def generar_descripcion_larga_desde_existente():
    data = request.json
    nombre_producto = data.get("nombre_producto")
    descripcion_larga_actual = data.get("descripcion_larga_actual", "")

    if not nombre_producto:
        return jsonify({"error": "Falta nombre_producto"}), 400

    texto = generar_descripcion_larga_desde_existente_groq(nombre_producto, descripcion_larga_actual)
    return jsonify({
        "descripcion_larga": texto,
        "success": True
    })

def validar_reseñas_antes_de_insertar(reseñas, conn):
    """
    Devuelve True si NO hay duplicados y se pueden insertar.
    Si hay alguna duplicada (autor o texto), devuelve False.
    """
    if not reseñas:
        return True

    with conn.cursor() as cursor:
        for review in reseñas:
            autor = review.get("autor")
            texto = review.get("texto")

            sql_check = """
                SELECT COUNT(*) as total
                FROM reseñas
                WHERE autor = %s OR texto = %s
            """
            cursor.execute(sql_check, (autor, texto))
            row = cursor.fetchone()
            if row and row["total"] > 0:
                logging.warning(f"❌ Reseña duplicada encontrada: autor={autor} o texto repetido.")
                return False

    return True

@app.route("/productos", methods=["GET"])
def obtener_productos():
    conn = basedatos_seo()
    productos = []
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT 
                    p.id_product,
                    p.nombre_producto,
                    p.img_url,
                    d_larga.texto AS descripcion_larga,
                    d_meta_title.texto AS meta_title,
                    d_meta_description.texto AS meta_description
                FROM productos p
                LEFT JOIN descripciones d_larga
                    ON p.id_product = d_larga.id_product AND d_larga.tipo = 'larga'
                LEFT JOIN descripciones d_meta_title
                    ON p.id_product = d_meta_title.id_product AND d_meta_title.tipo = 'meta_title'
                LEFT JOIN descripciones d_meta_description
                    ON p.id_product = d_meta_description.id_product AND d_meta_description.tipo = 'meta_description'
                ORDER BY p.fecha_creacion DESC
            """
            cursor.execute(sql)
            rows = cursor.fetchall()

            for row in rows:
                productos.append({
                    "id_product": row["id_product"],
                    "nombre_producto": row["nombre_producto"],
                    "img_url": row["img_url"],
                    "descripcion_larga": row["descripcion_larga"],
                    "meta_title": row["meta_title"],
                    "meta_description": row["meta_description"],
                    "ya_existe_en_seo": True
                })

        return jsonify({"success": True, "productos": productos})

    except Exception as e:
        logging.exception("Error obteniendo productos:")
        return jsonify({"success": False, "error": "Error interno obteniendo productos."}), 500

    finally:
        conn.close()

@app.route("/producto/<id_product>", methods=["PUT"])
def actualizar_producto(id_product):
    data = request.get_json()

    nombre_producto = data.get("nombre_producto")
    img_url = data.get("img_url")
    descripcion_larga = data.get("descripcion_larga")
    meta_title = data.get("meta_title")
    meta_description = data.get("meta_description")
    reseñas = data.get("reseñas", [])
    sincronizar = data.get("sincronizar", False)   # ✅ NUEVO

    if not nombre_producto:
        return jsonify({"success": False, "error": "Falta nombre_producto"}), 400

    conn = basedatos_seo()
    try:
        with conn.cursor() as cursor:
            # ✅ Verificar si existe el producto
            sql_check_product = """
                SELECT COUNT(*) as total
                FROM productos
                WHERE id_product = %s
            """
            cursor.execute(sql_check_product, (id_product,))
            existe = cursor.fetchone()

            if existe["total"] == 0:
                # No existe → insertar
                sql_insert_product = """
                    INSERT INTO productos (id_product, nombre_producto, img_url, fecha_creacion)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(sql_insert_product, (
                    id_product,
                    nombre_producto,
                    img_url,
                    datetime.now()
                ))
                logging.info(f"✅ Producto {id_product} insertado en tabla productos.")
            else:
                # Sí existe → actualizar
                sql_update_product = """
                    UPDATE productos
                    SET nombre_producto = %s,
                        img_url = %s
                    WHERE id_product = %s
                """
                cursor.execute(sql_update_product, (nombre_producto, img_url, id_product))
                logging.info(f"✅ Producto {id_product} actualizado en tabla productos.")

            # ➡ Actualizar o insertar descripciones
            for tipo, texto in [
                ("larga", descripcion_larga),
                ("meta_title", meta_title),
                ("meta_description", meta_description)
            ]:
                if texto is not None:
                    sql_check_desc = """
                        SELECT COUNT(*) as total
                        FROM descripciones
                        WHERE id_product = %s AND tipo = %s
                    """
                    cursor.execute(sql_check_desc, (id_product, tipo))
                    existe_desc = cursor.fetchone()

                    if existe_desc["total"] > 0:
                        sql_update_desc = """
                            UPDATE descripciones
                            SET texto = %s
                            WHERE id_product = %s AND tipo = %s
                        """
                        cursor.execute(sql_update_desc, (texto, id_product, tipo))
                        logging.info(f"✅ Descripción {tipo} actualizada.")
                    else:
                        sql_insert_desc = """
                            INSERT INTO descripciones (id_product, tipo, texto, fecha_creacion)
                            VALUES (%s, %s, %s, %s)
                        """
                        cursor.execute(sql_insert_desc, (id_product, tipo, texto, datetime.now()))
                        logging.info(f"✅ Descripción {tipo} insertada.")

            # ➡ Procesar reseñas
            reseñas_nuevas = []
            for review in reseñas:
                autor = review.get("autor")
                existente = review.get("existente", False)

                if existente:
                    sql_update_review = """
                        UPDATE reseñas
                        SET titulo = %s,
                            estrellas = %s,
                            texto = %s
                        WHERE id_product = %s AND autor = %s
                    """
                    cursor.execute(sql_update_review, (
                        review.get("titulo"),
                        int(round(float(review.get("estrellas", 0)))),
                        review.get("texto"),
                        id_product,
                        autor
                    ))
                    logging.info(f"✅ Reseña de autor {autor} actualizada.")
                else:
                    reseñas_nuevas.append(review)

            if reseñas_nuevas:
                es_valido = validar_reseñas_antes_de_insertar(reseñas_nuevas, conn)
                if not es_valido:
                    logging.warning("🔄 Generando reseñas nuevas con IA por duplicados encontrados...")
                    reseñas_nuevas = generar_y_validar_reseñas(nombre_producto, descripcion_larga, conn)

            for review in reseñas_nuevas:
                sql_insert_review = """
                    INSERT INTO reseñas
                    (id_product, titulo, autor, estrellas, texto, active, fecha_creacion)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql_insert_review, (
                    id_product,
                    review.get("titulo"),
                    review.get("autor"),
                    int(round(float(review.get("estrellas", 0)))),
                    review.get("texto"),
                    1,                       # ← aquí añadimos active = 1
                    datetime.now(),
                ))
                logging.info(f"✅ Insertada reseña de autor {review.get('autor')}")

        conn.commit()

        # ✅ NUEVO: solo sincronizar si lo indica el frontend
        if sincronizar:
            reseñas_finales = obtener_reseñas_seo(id_product)

            guardar_datos_en_prestashop(
                id_product=id_product,
                nombre_producto=nombre_producto,
                descripcion_larga=descripcion_larga,
                meta_title=meta_title,
                meta_description=meta_description,
                reseñas=reseñas_finales
            )
            logging.info(f"✅ Producto {id_product} sincronizado con PrestaShop.")
        else:
            logging.info(f"✅ Guardado solo en SEO. No se sincronizó con PrestaShop para producto {id_product}")

        return jsonify({"success": True})

    except Exception as e:
        conn.rollback()
        logging.exception("Error actualizando producto:")
        return jsonify({"success": False, "error": "Error interno al actualizar producto."}), 500

    finally:
        conn.close()

@app.route("/prestashop/reviews/producto/<id_product>", methods=["GET"])
def obtener_reseñas_producto_prestashop(id_product):
    """
    Devuelve TODAS las reseñas de un producto en PrestaShop.
    """
    conn = basedatos_prestashop()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT
                    id_product,
                    customer_name,
                    title,
                    comment,
                    rating,
                    status,
                    date_add
                FROM ps_iqitreviews_products
                WHERE id_product = %s
            """
            cursor.execute(sql, (id_product,))
            rows = cursor.fetchall()

            reseñas = []
            for row in rows:
                reseñas.append({
                    "id_product": row["id_product"],
                    "autor": row["customer_name"],
                    "titulo": row["title"],
                    "texto": row["comment"],
                    "estrellas": row["rating"],
                    "status": row["status"],
                    "date_add": row["date_add"].strftime("%Y-%m-%d %H:%M:%S") if row["date_add"] else None
                })

        return jsonify({"success": True, "reseñas": reseñas})

    except Exception as e:
        logging.exception(f"Error obteniendo reseñas para producto {id_product}:")
        return jsonify({"success": False, "error": "Error interno."}), 500

    finally:
        conn.close()

@app.route("/prestashop/reviews/guardar", methods=["POST"])
def guardar_reseñas_en_prestashop():
    """
    Guarda reseñas solo en PrestaShop.
    """
    data = request.get_json()
    id_product = data.get("id_product")
    reseñas = data.get("reseñas", [])

    if not id_product:
        return jsonify({"success": False, "error": "Falta id_product."}), 400

    conn_presta = basedatos_prestashop()
    try:
        with conn_presta.cursor() as cursor:
            # Borrar todas las reseñas antiguas
            sql_delete = """
                DELETE FROM ps_iqitreviews_products
                WHERE id_product = %s
            """
            cursor.execute(sql_delete, (id_product,))
            logging.info(f"🗑️ Reseñas antiguas eliminadas en PrestaShop para producto {id_product}")

            # Insertar nuevas reseñas
            for review in reseñas:
                sql_insert = """
                    INSERT INTO ps_iqitreviews_products
                    (id_product, customer_name, title, comment, rating, status, date_add)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """
                cursor.execute(sql_insert, (
                    id_product,
                    review.get("autor"),
                    review.get("titulo"),
                    review.get("texto"),
                    int(round(float(review.get("estrellas", 0)))),
                    int(review.get("status", 1))
                ))
                logging.info(f"✅ Reseña insertada en PrestaShop: autor={review.get('autor')}")

        conn_presta.commit()
        return jsonify({"success": True})

    except Exception as e:
        conn_presta.rollback()
        logging.exception("Error guardando reseñas en PrestaShop:")
        return jsonify({"success": False, "error": "Error guardando en PrestaShop."}), 500

    finally:
        conn_presta.close()

@app.route("/prestashop/reviews/productos", methods=["GET"])
def listar_productos_con_reseñas_prestashop():
    conn_presta = basedatos_prestashop()
    conn_seo = basedatos_seo()

    try:
        productos = []

        with conn_presta.cursor() as cursor:
            sql = """
                SELECT
                    r.id_product,
                    pl.name AS nombre_producto,
                    COUNT(r.id_product) AS total_reseñas,
                    SUM(CASE WHEN r.status = 1 THEN 1 ELSE 0 END) AS total_reseñas_activas,
                    MIN(r.status) AS min_status,
                    AVG(r.rating) AS media_estrellas,
                    MAX(r.date_add) AS ultima_fecha_reseña
                FROM ps_iqitreviews_products r
                LEFT JOIN ps_product_lang pl
                    ON r.id_product = pl.id_product
                    AND pl.id_lang = 1
                GROUP BY r.id_product, pl.name
                ORDER BY ultima_fecha_reseña DESC
            """
            cursor.execute(sql)
            rows = cursor.fetchall()

            # Imprimir filas brutas para depuración
            #logging.debug(">>> FILAS BRUTAS OBTENIDAS DE MYSQL:")
            #for row in rows:
                #logging.debug(row)

        if not rows:
            return jsonify({"success": True, "productos": []})

        # ✅ Usamos claves de diccionario
        ids = [row["id_product"] for row in rows]

        existe_en_seo = {}
        if ids:
            with conn_seo.cursor() as cursor:
                sql_check = f"""
                    SELECT id_product
                    FROM productos
                    WHERE id_product IN ({','.join(['%s'] * len(ids))})
                """
                cursor.execute(sql_check, ids)
                seo_rows = cursor.fetchall()

            seo_ids = {r["id_product"] for r in seo_rows}
            existe_en_seo = {id_: True for id_ in seo_ids}

        for row in rows:
            productos.append({
                "id_product": row["id_product"],
                "nombre_producto": row["nombre_producto"],
                "total_reseñas": int(row["total_reseñas"]),
                "total_reseñas_activas": int(row["total_reseñas_activas"]),
                "todas_activas": row["min_status"] == 1,
                "media_estrellas": float(row["media_estrellas"]) if row["media_estrellas"] is not None else 0,
                "ya_existe_en_seo": existe_en_seo.get(row["id_product"], False)
            })

        return jsonify({"success": True, "productos": productos})

    except Exception as e:
        logging.exception("Error obteniendo productos con reseñas en PrestaShop:")
        return jsonify({"success": False, "error": "Error interno."}), 500

    finally:
        conn_presta.close()
        conn_seo.close()

@app.route("/reseñas")
def vista_reseñas():
    return render_template("reseñas.html")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5012, debug=False)