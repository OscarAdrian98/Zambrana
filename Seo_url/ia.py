from groq import Groq
import json
import re
from faker import Faker
import logging
import db.config as config

# 👉 PON AQUÍ TU API KEY DE GROQ
API_KEY_GROQ = config.Clave

# Crea cliente Groq
client = Groq(api_key=API_KEY_GROQ)

# Instancia Faker en español
fake = Faker("es_ES")


def generar_nombre_autor_unico(conn, max_intentos=10):
    """
    Genera un nombre aleatorio en español que NO exista ya en la tabla reseñas.
    Devuelve None si tras varios intentos no encuentra uno libre.
    """
    for intento in range(max_intentos):
        nombre = f"{fake.first_name()} {fake.last_name()}"
        with conn.cursor() as cursor:
            sql = """
                SELECT COUNT(*) as total
                FROM reseñas
                WHERE autor = %s
            """
            cursor.execute(sql, (nombre,))
            existe = cursor.fetchone()
            if existe["total"] == 0:
                return nombre

    # Tras varios intentos, devuelve un nombre aunque no se sepa único
    logging.warning("⚠️ No se pudo generar autor único tras varios intentos. Se devuelve nombre aleatorio sin comprobar.")
    return f"{fake.first_name()} {fake.last_name()}"


def generar_reseñas_groq(nombre_producto, descripcion_larga, conn):
    prompt = f"""
Eres un cliente real que escribe reseñas auténticas para productos de motocross y enduro en tiendas online. Hablas español.

✅ Devuelve SOLO el JSON solicitado. NO escribas ningún texto fuera del JSON. NO utilices bloques de código (no pongas ```json ni nada similar).

Genera exactamente 1 reseña realista para el producto: {nombre_producto}.

Basadas en la siguiente descripción del producto:

{descripcion_larga}

Cada reseña debe incluir:
- "titulo": breve, máximo 8 palabras, en español. SIN saltos de línea ni tabulaciones.
- "autor": escribe siempre el texto "placeholder". Yo sustituiré luego el autor en Python.
- "estrellas": número entero (no decimales), entre 3 y 5.
- "texto": texto breve y natural en español, SIN saltos de línea ni tabulaciones. TODO en una sola línea.

✅ Devuelve exclusivamente este JSON TODO en una sola línea (sin saltos de línea ni tabulaciones):

[
  {{
    "titulo": "...",
    "autor": "placeholder",
    "estrellas": número,
    "texto": "..."
  }},
  ...
]
"""

    completion = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[
            {
                "role": "system",
                "content": "Eres un generador de reseñas auténticas para ecommerce especializado en motocross y enduro, en español."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.7
    )

    respuesta_texto = completion.choices[0].message.content.strip()
    print("Respuesta cruda Groq:", repr(respuesta_texto))

    # Quitar marcas de bloque de código
    if respuesta_texto.startswith("```json"):
        respuesta_texto = respuesta_texto.replace("```json", "")
        respuesta_texto = respuesta_texto.replace("```", "")
        respuesta_texto = respuesta_texto.strip()

    # Eliminar saltos de línea dentro de strings
    def limpiar_string(match):
        texto = match.group(0)
        texto = texto.replace("\n", " ").replace("\t", " ")
        texto = " ".join(texto.split())
        return texto

    respuesta_texto = re.sub(r'"(.*?)"', limpiar_string, respuesta_texto)
    respuesta_texto = respuesta_texto.replace("\n", " ")
    respuesta_texto = respuesta_texto.replace("\t", " ")
    respuesta_texto = " ".join(respuesta_texto.split())

    start = respuesta_texto.find("[")
    end = respuesta_texto.rfind("]")

    if start != -1 and end != -1:
        respuesta_texto = respuesta_texto[start:end+1]
    else:
        if respuesta_texto.endswith('}"'):
            respuesta_texto = respuesta_texto[:-2] + "}]"
        elif respuesta_texto.endswith('}'):
            respuesta_texto = respuesta_texto + "]"
        elif respuesta_texto.endswith('"'):
            respuesta_texto = respuesta_texto[:-1] + "\"}]"
        else:
            respuesta_texto = respuesta_texto + "}]"

        if not respuesta_texto.startswith("["):
            respuesta_texto = "[" + respuesta_texto

    respuesta_texto = respuesta_texto.rstrip("'")

    try:
        reseñas = json.loads(respuesta_texto)

        for review in reseñas:
            autor_unico = generar_nombre_autor_unico(conn)
            review["autor"] = autor_unico

        return reseñas

    except json.JSONDecodeError as e:
        print("❌ Error al parsear JSON:", e)
        print("Contenido recibido:", respuesta_texto)
        return []


def generar_meta_title_groq(nombre_producto, descripcion_larga):
    prompt = f"""
Eres un redactor SEO experto en ecommerce de motocross y enduro. Hablas español.

Genera un META TITLE en español para el producto: {nombre_producto}

- Basado tanto en el nombre del producto como en su descripción larga:
{descripcion_larga}

- Máximo 70 caracteres recomendado (puede ser algo menos, nunca más de 75).
- Que sea natural, comercial, atractivo y optimizado para SEO.
- Evita palabras genéricas como "compra", "oferta", "precio", salvo que sea relevante.
- No utilices etiquetas HTML ni comillas ni texto adicional.

✅ Devuelve SOLO el texto plano. Sin JSON, sin etiquetas, sin bloques de código.
"""

    completion = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[
            {
                "role": "system",
                "content": "Eres un generador de meta titles SEO en español para ecommerce especializado en motocross y enduro."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.7
    )

    respuesta_texto = completion.choices[0].message.content.strip()
    print("Meta Title generado:", repr(respuesta_texto))
    return respuesta_texto


def generar_meta_description_groq(nombre_producto, descripcion_larga):
    prompt = f"""
Eres un redactor SEO experto en ecommerce de motocross y enduro. Hablas español.

Genera una META DESCRIPTION en español para el producto: {nombre_producto}

- Basada tanto en el nombre del producto como en su descripción larga:
{descripcion_larga}

- Máximo 160 caracteres recomendado (puede ser algo menos, nunca más de 170).
- Debe ser natural, comercial, convincente y orientada a SEO.
- No uses términos de otros deportes (como golf, running, ciclismo, etc.).
- No utilices etiquetas HTML ni comillas ni texto adicional.

✅ Devuelve SOLO el texto plano. Sin JSON, sin etiquetas, sin bloques de código.
"""

    completion = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[
            {
                "role": "system",
                "content": "Eres un generador de meta descriptions SEO en español para ecommerce especializado en motocross y enduro."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.7
    )

    respuesta_texto = completion.choices[0].message.content.strip()
    print("Meta Description generada:", repr(respuesta_texto))
    return respuesta_texto


def generar_descripcion_larga_groq(nombre_producto):
    prompt = f"""
Eres un redactor SEO experto en tiendas online de motocross y enduro. Hablas español.

Genera una descripción LARGA en ESPAÑOL para el producto: {nombre_producto}.

- Este producto es SIEMPRE ropa, accesorios o equipamiento de motocross o enduro, nunca de otros deportes.
- Máximo 250 palabras.
- Debe ser detallada, atractiva y optimizada para SEO.
- Incluye características, beneficios y motivos de compra específicos para motocross o enduro.
- Integra palabras clave de forma natural en el texto, no en bloques al final.
- Usa lenguaje comercial y convincente, adaptado a ecommerce en español.
- Sin errores gramaticales ni ortográficos.
- No uses etiquetas HTML ni formato especial.
- No incluyas comillas alrededor del texto. Devuelve solo texto plano, sin nada extra.

✅ Devuelve SOLO el texto plano en español. No escribas JSON, etiquetas HTML ni texto adicional antes o después.
"""

    completion = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[
            {
                "role": "system",
                "content": "Eres un generador de descripciones largas SEO en español para ecommerce especializado en motocross y enduro."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.7
    )

    respuesta_texto = completion.choices[0].message.content.strip()
    print("Descripción larga generada:", repr(respuesta_texto))
    return respuesta_texto


def generar_descripcion_larga_desde_existente_groq(nombre_producto, descripcion_larga_actual):
    prompt = f"""
Eres un redactor SEO experto en tiendas online de motocross y enduro. Hablas español.

Tienes este NOMBRE DE PRODUCTO:
→ {nombre_producto}

Y esta DESCRIPCIÓN LARGA ACTUAL:
→ {descripcion_larga_actual}

✅ Genera una NUEVA descripción larga mejorada en ESPAÑOL para el mismo producto, usando tanto el nombre como la descripción larga original, pero mejorándola si es posible. Si la descripción actual es incompleta o mala, crea una completamente nueva basada en el nombre.

- Máximo 250 palabras.
- Debe ser detallada, atractiva y optimizada para SEO.
- Incluye características, beneficios y motivos de compra específicos para motocross o enduro.
- Integra palabras clave de forma natural en el texto.
- Usa lenguaje comercial y convincente.
- Sin errores gramaticales ni ortográficos.
- No uses etiquetas HTML ni formato especial.
- No incluyas comillas alrededor del texto. Devuelve solo texto plano, sin nada extra.

✅ Devuelve EXCLUSIVAMENTE el texto plano en español. No escribas JSON ni bloques de código ni nada adicional.
"""

    completion = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[
            {
                "role": "system",
                "content": "Eres un generador de descripciones largas SEO en español para ecommerce especializado en motocross y enduro."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.7
    )

    respuesta_texto = completion.choices[0].message.content.strip()
    print("Descripción larga (desde existente) generada:", repr(respuesta_texto))
    return respuesta_texto