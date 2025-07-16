import requests
from bs4 import BeautifulSoup

def scrapear_producto(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    # Nombre del producto
    nombre_tag = soup.select_one("h1.h1.page-title span")
    nombre_producto = nombre_tag.get_text(strip=True) if nombre_tag else None

    # Descripción corta
    descripcion_corta_tag = soup.select_one(".product_header_container .product-description")
    descripcion_corta_texto = (
        descripcion_corta_tag.get_text(strip=True) if descripcion_corta_tag else None
    )

    # Descripción larga
    descripcion_div = soup.select_one(".product-description .rte-content")
    elementor_div = soup.select_one(".product-description .elementor")

    texto_rte = descripcion_div.get_text(separator=" ", strip=True) if descripcion_div else ""
    texto_elementor = elementor_div.get_text(separator=" ", strip=True) if elementor_div else ""

    descripcion_texto = (texto_rte + " " + texto_elementor).strip() or None

    # id_product
    id_product_input = soup.find("input", {"id": "product_page_product_id"})
    id_product = id_product_input["value"] if id_product_input else None

    # Imagen principal
    imagen_tag = soup.select_one(".product-lmage-large img")
    imagen_url = (
        imagen_tag.get("data-image-large-src")
        if imagen_tag and imagen_tag.has_attr("data-image-large-src")
        else None
    )

    # Meta title
    title_tag = soup.find("title")
    meta_title = title_tag.get_text(strip=True) if title_tag else None

    # Meta description
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = (
        meta_desc_tag["content"]
        if meta_desc_tag and meta_desc_tag.has_attr("content")
        else None
    )

    return (
        id_product,
        nombre_producto,
        descripcion_corta_texto,
        descripcion_texto,
        imagen_url,
        meta_title,
        meta_description,
    )