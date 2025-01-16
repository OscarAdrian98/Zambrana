from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium import webdriver
from bs4 import BeautifulSoup
import time
import openpyxl
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuración del driver de Selenium
def init_driver():
    """Inicializa el driver de Selenium."""
    options = webdriver.ChromeOptions()
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-webgpu')  # Deshabilitar WebGPU
    options.add_argument('--disable-software-rasterizer')  # Deshabilitar renderizado por software
    options.add_argument("--headless")  # Ejecutar en modo headless
    options.add_argument('--no-sandbox')
    options.add_argument('--start-maximized')
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    driver_service = Service('\\scraping_ref\\chromedriver.exe') # Pon la ruta correcta a tu chromedriver
    driver = webdriver.Chrome(service=driver_service, options=options)
    return driver

def wait_and_find_element(driver, by, value, timeout=10, message=None):
    """Función auxiliar para esperar y encontrar elementos de manera segura"""
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
        return element
    except Exception as e:
        print(f"Error encontrando elemento {value}: {e}")
        if message:
            print(message)
        return None

def get_compressed_html(element):
    """Función para obtener el HTML comprimido de un elemento"""
    if element:
        html_content = element.get_attribute('innerHTML')
        # Eliminar espacios en blanco extra y saltos de línea
        compressed = ' '.join(html_content.split())
        return compressed
    return "Descripción no encontrada"

def scrape_az_offroad(reference):
    driver = init_driver()
    try:
        # Usar el enlace directo para buscar la referencia
        search_url = f"https://az-offroad.com/m/ambjolisearch/jolisearch?s={reference}"
        driver.get(search_url)
        print(f"Página de búsqueda cargada para referencia '{reference}'.")

        # Aceptar cookies
        try:
            cookies_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.lgcookieslaw-accept-button"))
            )
            cookies_button.click()
            print("Cookies aceptadas en AZ-Offroad.")
        except Exception as e:
            print(f"No se encontraron cookies para aceptar o no fue necesario: {e}")

        # Esperar y hacer clic en el producto
        try:
            product_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.thumbnail.product-thumbnail"))
            )
            driver.execute_script("arguments[0].click();", product_element)
            print("Se hizo clic en el producto.")
            time.sleep(3)  # Esperar a que la página cargue
        except Exception as e:
            print(f"No se pudo hacer clic en el producto: {e}")
            return None

        # Extraer información del producto
        try:
            # Nombre del producto
            name_element = driver.find_element(By.CSS_SELECTOR, "h1.h1.page-title span")
            name = name_element.text.strip() if name_element else "Nombre no encontrado"

            # Referencia del producto
            ref_element = driver.find_element(By.CSS_SELECTOR, "div.product-reference span")
            ref_competencia = ref_element.text.strip() if ref_element else "Referencia no encontrada"

            # PVP
            pvp_element = driver.find_element(By.CSS_SELECTOR, "span.regular-price")
            pvp = pvp_element.text.strip() if pvp_element else "PVP no encontrado"

            # Precio final
            final_price_element = driver.find_element(By.CSS_SELECTOR, "span.product-price.current-price-value")
            final_price = final_price_element.text.strip() if final_price_element else "Precio final no encontrado"

            # Descuento
            try:
                # Intentar buscar descuento en porcentaje
                discount_element = driver.find_element(By.CSS_SELECTOR, "span.badge.badge-discount.discount-percentage")
                discount = discount_element.text.strip()
            except NoSuchElementException:
                # Intentar buscar descuento en importe
                try:
                    discount_element = driver.find_element(By.CSS_SELECTOR, "span.badge.badge-discount.discount-amount")
                    discount = discount_element.text.strip()
                except NoSuchElementException:
                    discount = "Sin descuento"

            print("Información del producto extraída correctamente.")
            return {
                "name": name,
                "ref_competencia": ref_competencia,
                "pvp": pvp,
                "final_price": final_price,
                "discount": discount,
                "competencia": "AZ-Offroad"
            }
        except Exception as e:
            print(f"Error al extraer información del producto: {e}")
            return None

    except Exception as e:
        print(f"Error general en AZ-Offroad: {e}")
        return None

    finally:
        driver.quit()


def scrape_product(reference):
    driver = init_driver()
    try:
        base_url = "https://www.greenlandmx.com/en-int/"
        driver.get(base_url)
        print("Página principal cargada.")

        # Manejar cookies
        try:
            cookies_button = wait_and_find_element(
                driver,
                By.ID,
                'CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
                timeout=5,
                message="Esperando botón de cookies..."
            )
            if cookies_button and cookies_button.is_displayed():
                cookies_button.click()
                print("Cookies aceptadas.")
                time.sleep(2)
        except Exception as e:
            print(f"No se pudieron aceptar las cookies: {e}")

        # Abrir el cuadro de búsqueda correctamente
        try:
            search_trigger = wait_and_find_element(
                driver,
                By.CLASS_NAME,
                "mini-search__trigger",
                timeout=5,
                message="Esperando trigger del buscador..."
            )

            if not search_trigger:
                raise Exception("No se encontró el trigger del buscador")

            driver.execute_script("arguments[0].click();", search_trigger)
            print("Trigger del buscador clickeado.")
            time.sleep(2)

            search_input = wait_and_find_element(
                driver,
                By.CLASS_NAME,
                "dfd-searchbox-input",
                timeout=5,
                message="Esperando campo de entrada del buscador..."
            )

            if not search_input:
                raise Exception("No se encontró el campo de entrada del buscador")

            search_input.clear()
            search_input.send_keys(reference)
            search_input.send_keys(Keys.RETURN)
            print(f"Referencia '{reference}' buscada.")
            time.sleep(2)
        except Exception as e:
            print(f"Error durante la búsqueda: {e}")
            return None

        # Procesar resultados
        try:
            product_link = wait_and_find_element(
                driver,
                By.CLASS_NAME,
                'dfd-card-link',
                timeout=5,
                message="Esperando enlace del producto..."
            )

            if not product_link:
                raise Exception("No se encontró el enlace del producto")

            product_url = product_link.get_attribute('href')
            driver.get(product_url)
            print(f"Navegando a la página del producto: {product_url}")
            time.sleep(2)

            # Obtener el nombre del producto
            name_element = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "p.base.title-font",
                timeout=5,
                message="Esperando nombre del producto..."
            )
            name = name_element.text.strip() if name_element else "Nombre no encontrado"

            # Obtener PVP original
            pvp_element = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "div.old-price span.price",  # Selector ajustado para el PVP
                timeout=5,
                message="Buscando PVP en Greenland..."
            )
            pvp = pvp_element.text.strip().replace("PVP ", "") if pvp_element else "PVP no encontrado"


            # Obtener descuento
            discount_element = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "span.text-white.bg-danger",
                timeout=5,
                message="Buscando descuento..."
            )
            discount = discount_element.text.strip() if discount_element else "Sin descuento"

            # Obtener precio final
            final_price_element = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "div.final-price span.price",  # Selector ajustado
                timeout=5,
                message="Esperando precio final en Greenland..."
            )
            final_price = final_price_element.text.strip() if final_price_element else "Precio final no encontrado"


            # Obtener referencia de la competencia
            ref_competencia_element = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "div.flex.text-xs.text-grey.order-2.text-sm div.value",
                timeout=5,
                message="Buscando referencia en Greenland..."
            )
            ref_competencia = ref_competencia_element.text.strip() if ref_competencia_element else "Referencia no encontrada"

            # Obtener descripción
            description_element = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "div.prose",
                timeout=5,
                message="Buscando descripción del producto..."
            )
            description = get_compressed_html(description_element)

            # Obtener imagen
            image_element = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "div.main-img img",
                timeout=5,
                message="Buscando imagen del producto..."
            )
            image_url = image_element.get_attribute('src') if image_element else "Imagen no encontrada"

            return {
                "name": name,
                "pvp": pvp,
                                "discount": discount,
                "final_price": final_price,
                "description": description,
                "image_url": image_url,
                "ref_competencia": ref_competencia,
                "competencia": "Greenland"
            }

        except Exception as e:
            print(f"Error al procesar el producto en Greenland: {e}")
            return None

    except Exception as e:
        print(f"Error general en Greenland: {e}")
        return None
    
    finally:
        driver.quit()

def scrape_motocross_center(reference):
    driver = init_driver()
    try:
        base_url = "https://www.motocrosscenter.com/shop/es/"
        driver.get(base_url)
        print("Página de Motocross Center cargada.")

        # Manejar cookies
        try:
            cookies_button = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "button.lgcookieslaw-accept-button",
                timeout=5,
                message="Esperando botón de cookies en Motocross Center..."
            )
            if cookies_button and cookies_button.is_displayed():
                cookies_button.click()
                print("Cookies aceptadas en Motocross Center.")
                time.sleep(2)
        except Exception as e:
            print(f"No se pudieron aceptar las cookies en Motocross Center: {e}")

        # Buscar la referencia en el buscador
        try:
            search_input = wait_and_find_element(
                driver,
                By.ID,
                "search_query_top",
                timeout=5,
                message="Esperando campo de entrada del buscador en Motocross Center..."
            )

            if not search_input:
                raise Exception("No se encontró el campo de entrada del buscador en Motocross Center")

            search_input.clear()
            search_input.send_keys(reference)
            time.sleep(1)

            search_button = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "button.button-search",
                timeout=5,
                message="Esperando botón de búsqueda en Motocross Center..."
            )

            if search_button:
                search_button.click()
            else:
                search_input.send_keys(Keys.RETURN)

            print(f"Referencia '{reference}' buscada en Motocross Center.")
            time.sleep(2)
        except Exception as e:
            print(f"Error durante la búsqueda en Motocross Center: {e}")
            return None

        # Seleccionar el producto de los resultados
        try:
            product_link = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "a.df-card__image",
                timeout=5,
                message="Esperando enlace del producto en Motocross Center..."
            )

            if not product_link:
                raise Exception("No se encontró el enlace del producto en Motocross Center")

            product_url = product_link.get_attribute('href')
            driver.get(product_url)
            print(f"Navegando a la página del producto en Motocross Center: {product_url}")
            time.sleep(2)

            # Extraer el nombre del producto
            name_element = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "div.container > h1",
                timeout=5,
                message="Buscando nombre del producto en Motocross Center..."
            )
            name = name_element.text.strip() if name_element else "Nombre no encontrado"

            # Extraer el precio final
            final_price_element = wait_and_find_element(
                driver,
                By.ID,
                "our_price_display",
                timeout=5,
                message="Buscando precio final en Motocross Center..."
            )
            final_price = final_price_element.text.strip() if final_price_element else "Precio final no encontrado"

            # Extraer el PVP
            pvp_element = wait_and_find_element(
                driver,
                By.ID,
                "old_price_display",
                timeout=5,
                message="Buscando PVP en Motocross Center..."
            )
            pvp = pvp_element.text.strip() if pvp_element else "PVP no encontrado"

            # Extraer la referencia
            ref_element = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "p#product_reference span.editable",
                timeout=5,
                message="Buscando referencia en Motocross Center..."
            )
            ref_competencia = ref_element.text.strip() if ref_element else "Referencia no encontrada"

            # Extraer el descuento
            discount_element = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "span.sale-box span.sale-label",
                timeout=5,
                message="Buscando descuento en Motocross Center..."
            )
            if discount_element:
                discount_text = discount_element.text.strip()
                # Extraer solo el porcentaje usando una expresión regular
                import re
                match = re.search(r"-\d+%", discount_text)
                discount = match.group(0) if match else "Sin descuento"
            else:
                discount = "Sin descuento"

            # Extraer la descripción
            description_element = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "section",
                timeout=5,
                message="Buscando descripción en Motocross Center..."
            )
            description = get_compressed_html(description_element)

            # Extraer la URL de la imagen
            image_element = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "div.magic-slide.mt-active img[itemprop='image']",
                timeout=5,
                message="Buscando imagen en Motocross Center..."
            )
            image_url = image_element.get_attribute('src') if image_element else "Imagen no encontrada"

            return {
                "name": name,
                "pvp": pvp,
                "discount": discount,
                "final_price": final_price,
                "description": description,
                "image_url": image_url,
                "ref_competencia": ref_competencia,
                "competencia": "Motocross Center"
            }

        except Exception as e:
            print(f"Error al procesar el producto en Motocross Center: {e}")
            return None

    except Exception as e:
        print(f"Error general en Motocross Center: {e}")
        return None
    
    finally:
        driver.quit()

def scrape_motocard(reference):
    driver = init_driver()
    try:
        base_url = f"https://www.motocard.com/search?q={reference}&p=1&nidx"
        driver.get(base_url)
        print(f"Página de búsqueda en Motocard cargada para referencia '{reference}'.")

        # Esperar los resultados de búsqueda
        try:
            product_block = wait_and_find_element(
                driver,
                By.CSS_SELECTOR,
                "div.col.s6.m4.lc5 article.item",
                timeout=5,
                message="Esperando resultados de productos en Motocard..."
            )

            if not product_block:
                print(f"No se encontró la referencia '{reference}' en Motocard.")
                return None

            # Extraer el nombre del producto
            name_element = product_block.find_element(By.CSS_SELECTOR, "h3.heading-tag span:first-child")
            name = name_element.text.strip() if name_element else "Nombre no encontrado"

            # Extraer la referencia de la competencia
            ref_element = product_block.find_element(By.CSS_SELECTOR, "h3.heading-tag strong")
            ref_competencia = ref_element.text.strip() if ref_element else "Referencia no encontrada"

            # Extraer el precio final
            price_element = product_block.find_element(By.CSS_SELECTOR, "span.item__price")
            final_price = price_element.text.strip().split(" ")[0] if price_element else "Precio no encontrado"

            # Extraer el PVP
            old_price_element = product_block.find_element(By.CSS_SELECTOR, "span.item__old-price.strike")
            pvp = old_price_element.text.strip() if old_price_element else "PVP no encontrado"

            # Extraer el descuento
            try:
                discount_element = product_block.find_element(By.CSS_SELECTOR, "span.discount")
                discount = discount_element.text.strip() if discount_element else "Sin descuento"
            except Exception:
                discount = "Sin descuento"

            # Extraer la URL de la imagen
            try:
                image_element = product_block.find_element(By.CSS_SELECTOR, "span.product-image img")
                image_url = image_element.get_attribute("src") if image_element else "Imagen no encontrada"
            except Exception:
                image_url = "Imagen no encontrada"

            # Retornar los datos extraídos
            return {
                "name": name,
                "ref_competencia": ref_competencia,
                "pvp": pvp,
                "discount": discount,
                "final_price": final_price,
                "image_url": image_url,
                "competencia": "Motocard"
            }

        except Exception as e:
            print(f"Error durante la extracción en Motocard: {e}")
            return None

    except Exception as e:
        print(f"Error general en Motocard: {e}")
        return None
    
    finally:
        driver.quit()

def scrape_mxzambrana(reference):
    driver = init_driver()
    try:
        # Abrir el enlace de búsqueda directo
        search_url = f"https://mxzambrana.com/module/iqitsearch/searchiqit?s={reference}"
        driver.get(search_url)
        print(f"Página de búsqueda cargada para referencia '{reference}'.")

        # Aceptar cookies
        try:
            cookies_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.lgcookieslaw-accept-button"))
            )
            cookies_button.click()
            print("Cookies aceptadas en MX Zambrana.")
        except Exception as e:
            print(f"No se encontraron cookies para aceptar o no fue necesario: {e}")

        # Esperar y hacer clic en el producto
        try:
            product_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "article.product-miniature a.thumbnail"))
            )
            driver.execute_script("arguments[0].click();", product_element)
            print("Se hizo clic en el producto.")
            time.sleep(3)  # Esperar a que la página cargue
        except Exception as e:
            print(f"No se pudo hacer clic en el producto: {e}")
            return None

        # Extraer información del producto
        try:
            # Nombre del producto
            name_element = driver.find_element(By.CSS_SELECTOR, "h1.h1.page-title span")
            name = name_element.text.strip() if name_element else "Nombre no encontrado"

            # Referencia del producto
            ref_element = driver.find_element(By.CSS_SELECTOR, "div.product-reference span")
            ref_competencia = ref_element.text.strip() if ref_element else "Referencia no encontrada"

            # PVP
            pvp_element = driver.find_element(By.CSS_SELECTOR, "span.regular-price")
            pvp = pvp_element.text.strip() if pvp_element else "PVP no encontrado"

            # Precio final
            final_price_element = driver.find_element(By.CSS_SELECTOR, "span.product-price.current-price-value")
            final_price = final_price_element.text.strip() if final_price_element else "Precio final no encontrado"

            # Descuento
            try:
                # Intentar buscar descuento en porcentaje
                discount_element = driver.find_element(By.CSS_SELECTOR, "span.badge.badge-discount.discount-percentage")
                discount = discount_element.text.strip()
            except NoSuchElementException:
                # Intentar buscar descuento en importe
                try:
                    discount_element = driver.find_element(By.CSS_SELECTOR, "span.badge.badge-discount.discount-amount")
                    discount = discount_element.text.strip()
                except NoSuchElementException:
                    discount = "Sin descuento"

            print("Información del producto extraída correctamente.")
            return {
                "name": name,
                "ref_competencia": ref_competencia,
                "pvp": pvp,
                "final_price": final_price,
                "discount": discount,
                "competencia": "MX Zambrana"
            }
        except Exception as e:
            print(f"Error al extraer información del producto: {e}")
            return None

    except Exception as e:
        print(f"Error general en MX Zambrana: {e}")
        return None

    finally:
        driver.quit()

def scrape_moremotoracing(reference):
    driver = init_driver()
    try:
        # Construir la URL de búsqueda
        search_url = f"https://moremotoracing.com/busqueda?order=product.position.desc&s={reference}"
        driver.get(search_url)
        print(f"Página de búsqueda cargada para referencia '{reference}'.")

        # Aceptar cookies
        try:
            cookies_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.lgcookieslaw-accept-button"))
            )
            cookies_button.click()
            print("Cookies aceptadas en Moremotoracing.")
        except Exception as e:
            print(f"No se encontraron cookies para aceptar o no fue necesario: {e}")

        # Esperar y hacer clic en el producto
        try:
            product_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div.js-product-miniature a"))
            )
            driver.execute_script("arguments[0].click();", product_element)
            print("Se hizo clic en el producto.")
            time.sleep(3)  # Esperar a que la página cargue
        except Exception as e:
            print(f"No se pudo hacer clic en el producto: {e}")
            return None

        # Extraer información del producto
        try:
            # Nombre del producto
            name_element = driver.find_element(By.CSS_SELECTOR, "h1.product_title")
            name = name_element.text.strip() if name_element else "Nombre no encontrado"

            # Referencia del producto
            ref_element = driver.find_element(By.CSS_SELECTOR, "div.product-prices span")
            ref_competencia = ref_element.text.strip().replace("Ref: ", "") if ref_element else "Referencia no encontrada"

            # Precio final
            final_price_element = driver.find_element(By.CSS_SELECTOR, "div.current-price span[itemprop='price']")
            final_price = final_price_element.text.strip() if final_price_element else "Precio final no encontrado"

            # PVP
            pvp_element = driver.find_element(By.CSS_SELECTOR, "span.regular-price")
            pvp = pvp_element.text.strip() if pvp_element else "PVP no encontrado"

            # Descuento
            discount_element = driver.find_element(By.CSS_SELECTOR, "span.product-savings")
            if discount_element:
                discount_text = discount_element.text.strip()
                # Convertir "25%" a "-25%" si es un porcentaje
                if "%" in discount_text:
                    discount = f"-{discount_text.replace('Ahorra ', '').strip()}"
                else:
                    discount = discount_text.replace("Ahorra ", "").strip()
            else:
                discount = "Sin descuento"

            # Descripción
            description_element = driver.find_element(By.CSS_SELECTOR, "div.product-description")
            description = description_element.get_attribute('innerHTML') if description_element else "Descripción no encontrada"

            # Imagen
            image_element = driver.find_element(By.CSS_SELECTOR, "div.img-placeholder img")
            image_url = image_element.get_attribute('src') if image_element else "Imagen no encontrada"

            print("Información del producto extraída correctamente.")
            return {
                "name": name,
                "ref_competencia": ref_competencia,
                "pvp": pvp,
                "final_price": final_price,
                "discount": discount,
                "description": description,
                "image_url": image_url,
                "competencia": "Moremotoracing"
            }
        except Exception as e:
            print(f"Error al extraer información del producto: {e}")
            return None

    except Exception as e:
        print(f"Error general en Moremotoracing: {e}")
        return None

    finally:
        driver.quit()

def scrape_fcmoto(reference):
    driver = init_driver()
    try:
        # Construir la URL de búsqueda
        search_url = f"https://www.fc-moto.de/epages/fcm.sf/es_ES/?ObjectID=2587584&ViewAction=FacetedSearchProducts&SearchString={reference}"
        driver.get(search_url)
        print(f"Página de búsqueda cargada para referencia '{reference}'.")

        # Esperar y hacer clic en el producto
        try:
            product_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div.ListItemProductContainer a"))
            )
            product_url = product_element.get_attribute('href')
            driver.get(product_url)
            print(f"Se hizo clic en el producto. Navegando a {product_url}.")
            time.sleep(3)  # Esperar a que la página cargue
        except Exception as e:
            print(f"No se pudo hacer clic en el producto: {e}")
            return None

        # Extraer información del producto
        try:
            # Nombre del producto
            name_element = driver.find_element(By.CSS_SELECTOR, "h1.ProductDetailsHeadline span")
            name = name_element.text.strip() if name_element else "Nombre no encontrado"

            # Precio final
            final_price_element = driver.find_element(By.CSS_SELECTOR, "span.Price.PriceIsHot")
            final_price = final_price_element.text.strip() if final_price_element else "Precio final no encontrado"

            # PVP
            pvp_element = driver.find_element(By.CSS_SELECTOR, "span.LineThrough")
            pvp = pvp_element.text.strip() if pvp_element else "PVP no encontrado"

            # Descuento
            discount_element = driver.find_element(By.CSS_SELECTOR, "span.HotPriceNoImg")
            discount = discount_element.text.replace("Se ahorra ", "-").strip() if discount_element else "Sin descuento"

            # Descripción (Opcional)
            description_element = driver.find_element(By.CSS_SELECTOR, "div.ProductDescriptionText")
            description = description_element.text.strip() if description_element else "Descripción no encontrada"

            # Imagen
            image_element = driver.find_element(By.CSS_SELECTOR, "div.ImageArea img")
            image_url = image_element.get_attribute('src') if image_element else "Imagen no encontrada"

            print("Información del producto extraída correctamente.")
            return {
                "name": name,
                "pvp": pvp,
                "final_price": final_price,
                "discount": discount,
                "description": description,
                "image_url": image_url,
                "competencia": "FC-Moto"
            }
        except Exception as e:
            print(f"Error al extraer información del producto: {e}")
            return None

    except Exception as e:
        print(f"Error general en FC-Moto: {e}")
        return None

    finally:
        driver.quit()

def save_to_excel(data, filename="productos.xlsx", searched_reference=""):
    """
    Guarda los datos en un archivo Excel, incluyendo la referencia buscada.
    """
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Productos"

    # Escribir encabezados
    sheet.append([
        "Referencia Buscada", "Nombre", "PVP", "Descuento",
        "Precio Final", "Descripción", "Imagen", "Referencia Competencia", "Competencia"
    ])

    # Escribir datos
    for item in data:
        sheet.append([
            searched_reference,  # Aquí se agrega la referencia buscada
            item.get('name', ""),
            item.get('pvp', ""),
            item.get('discount', ""),
            item.get('final_price', ""),
            item.get('description', ""),
            item.get('image_url', ""),
            item.get('ref_competencia', ""),
            item.get('competencia', "")
        ])

    workbook.save(filename)
    print(f"Datos guardados en {filename}")

def buscar_referencia_parcial(reference):
    """
    Realiza la búsqueda de la referencia en todas las plataformas configuradas y envía resultados parciales.
    """
    # Configuración para habilitar o deshabilitar búsquedas en cada plataforma
    search_greenland = True  # Poner False si no quieres que busque en Greenland
    search_az_offroad = True  # Poner False si no quieres que busque en AZ-Offroad
    search_motocross = True  # Poner False si no quieres que busque en Motocross Center
    search_motocard = True  # Poner False si no quieres que busque en Motocard
    search_mxzambrana = True  # Poner False si no quieres que busque en MX Zambrana
    search_moremotoracing = True  # Poner False si no quieres que busque en Moremotoracing
    search_fcmoto = False  # Poner False si no quieres que busque en FC-Moto

    # Diccionario de plataformas activas
    plataformas = {
        "Greenland": scrape_product if search_greenland else None,
        "AZ-Offroad": scrape_az_offroad if search_az_offroad else None,
        "Motocross Center": scrape_motocross_center if search_motocross else None,
        "Motocard": scrape_motocard if search_motocard else None,
        "MX Zambrana": scrape_mxzambrana if search_mxzambrana else None,
        "Moremotoracing": scrape_moremotoracing if search_moremotoracing else None,
        "FC-Moto": scrape_fcmoto if search_fcmoto else None
    }

    # Filtrar las plataformas habilitadas
    plataformas_activas = {nombre: funcion for nombre, funcion in plataformas.items() if funcion}

    print(f"Buscando referencia: {reference}")

    # Ejecutar las búsquedas concurrentemente
    with ThreadPoolExecutor(max_workers=6) as executor:
        futuros = {executor.submit(funcion, reference): nombre for nombre, funcion in plataformas_activas.items()}

        for futuro in as_completed(futuros):
            plataforma = futuros[futuro]
            try:
                resultado = futuro.result()
                if resultado:
                    resultado['plataforma'] = plataforma
                    yield {"success": True, "result": resultado}
                else:
                    yield {"success": False, "message": f"No se encontró la referencia en {plataforma}."}
            except Exception as e:
                yield {"success": False, "error": f"Error en {plataforma}: {str(e)}"}