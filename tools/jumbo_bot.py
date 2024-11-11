''' 
Deberia poner una def con el login
y otra funcion hace la busqueda de productos y agrega al carrito donde el input es una lista de productos
'''     
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException



def initialize_driver(url):
    options = webdriver.ChromeOptions()
    options.add_argument('--window-size=1920,1080')  # Set window size
    options.add_argument('--headless')  # Enables headless mode
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get(url)  
    return driver
    
def login(email, password, address):
    driver = initialize_driver("https://www.jumbo.com.ar/login")
    # Wait for the "Ingresar con email y contraseña" button to load and click it
    ingresar_button = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.vtex-login-2-x-button.vtex-login-2-x-emailPasswordOptionBtn button"))
    )
    driver.execute_script("arguments[0].scrollIntoView();", ingresar_button)
    driver.execute_script("arguments[0].click();", ingresar_button)
    
    # Wait for the email input field to appear
    email_input = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'nombre@mail.com')]"))
    )
    
    # Input email and verify the value
    email_input.clear()  # Clear the field in case of any autofill
    email_input.send_keys(email)
    time.sleep(1)  # Short delay to ensure the value is registered
        
    # Wait for the password input field to appear
    password_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
    )

    # Input password and verify the value
    password_input.clear()
    password_input.send_keys(password)  # Replace "your-password" with the actual password
    time.sleep(1)  # Short delay to ensure the value is registered

    ''' a veces aparece una venta que me pide el email otra vez, ver que onda.
    Debería poner un if, no es un problema grande la verdad'''
    # Wait for the "Ingresar con email y contraseña" button to load and click it
    ingresar_button = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.vtex-login-2-x-sendButton button"))
    )
    driver.execute_script("arguments[0].scrollIntoView();", ingresar_button)
    driver.execute_script("arguments[0].click();", ingresar_button)

    time.sleep(10)
    metodo_entrega_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, ".jumboargentinaio-delivery-modal-1-x-containerTrigger.flex.flex-row.h-100.pointer a > span"))
    )
    driver.execute_script("arguments[0].scrollIntoView(true);", metodo_entrega_button)
    driver.execute_script("arguments[0].click();", metodo_entrega_button)

    metodo_entrega_button = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, ".jumboargentinaio-delivery-modal-1-x-selected button svg"))
    )
    driver.execute_script("arguments[0].scrollIntoView(true);", metodo_entrega_button)
    metodo_entrega_button.click()

    direccion = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Calle y Número ( Sin piso ni dpto)']")))  # Adjust the placeholder to match

# Input password and verify the value
    direccion.click()
    driver.execute_script("arguments[0].scrollIntoView(true);", direccion) # LO SACO?
    driver.execute_script("""
        arguments[0].focus();
        arguments[0].value = arguments[1];
        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
    """, direccion, address) # LO HAGO MAS SIMPLE?

     # Press Enter to trigger the dropdown (if needed)
    direccion.send_keys(Keys.RETURN)
    time.sleep(1)  # Short delay for the dropdown
    # Press Down Arrow to select the first suggestion
    direccion.send_keys(Keys.ARROW_DOWN)
    time.sleep(0.5)  # Short delay to ensure the selection
    # Press Enter to select the highlighted suggestion
    direccion.send_keys(Keys.RETURN)

    time.sleep(1)

    piso = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Ejemplo: 2']"))  # Adjust the placeholder to match
    )
    piso.click()
    time.sleep(1)
    piso.send_keys("Lote 16")  # Replace "your-password" with the actual password
    time.sleep(1)

    enviar_button = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".jumboargentinaio-delivery-modal-1-x-buttonStyleLCTrue button"))
    )
    driver.execute_script("arguments[0].scrollIntoView();", enviar_button)
    driver.execute_script("arguments[0].click();", enviar_button)

    continue_button = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, ".jumboargentinaio-delivery-modal-1-x-continueButton button"))
    )
    continue_button.click()

    return driver

def add_to_bag(url,driver):
    '''
    poner codigo, por ahora hacer con solo un url(producto)
    '''
    driver.get(url)

    time.sleep(5)

    # Wait and re-locate the button each time to avoid StaleElementReferenceException
    button = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Agregar']"))
    )

    # Click the button using JavaScript to avoid interception issues
    driver.execute_script("arguments[0].click();", button)
    print("Button clicked successfully.")

    time.sleep(8)

    return driver
   
def crear_lista(nombre_lista,driver):
    time.sleep(1)
    button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, ".buy-button-float button"))
    )
    driver.execute_script("arguments[0].scrollIntoView();", button) # esto creo que debo sacarlo
    time.sleep(2)
    driver.execute_script("arguments[0].click();", button)
    #button.click()
    time.sleep(10)

    button = WebDriverWait(driver, 11).until(
    EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Guardar compra en mis listas']"))
    )
    button.click()

    input_field = WebDriverWait(driver, 12).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Ejemplo: Lista Desayuno']"))
    )

    # Clear any existing text and input your text
    input_field.clear()
    input_field.send_keys(nombre_lista)

    time.sleep(1)


    # Wait until the "Guardar" button is clickable and then click it
    guardar_button = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Guardar']"))
    )
    guardar_button.click()
    print("Clicked the 'Guardar' button successfully.")
    time.sleep(10)

    return driver

from langchain_core.tools import tool


@tool("jumbo_bot")
def jumbo_bot(urls, email = "fegoulu@itba.edu.ar", password = "Londres1908", address = "Los bosques 1730"):
    """
    Tool utilizada para añadir productos al carrito.
    """
    from datetime import datetime
    nombre_lista = datetime.now()
    nombre_lista = nombre_lista.strftime("%Y-%m-%d %H:%M:%S")  # Adjust the format as needed

    start_time = time.time()

    print(f"Urls recibidos:  {urls}")
    driver = login(email, password, address)
    for url in urls:
        driver = add_to_bag(url,driver)

    driver = crear_lista(nombre_lista,driver)
    driver.quit()

    end_time = time.time()
    total_time = end_time - start_time

    # Prepare a result summary
    result_summary = {
        "message": "Process completed successfully",
        "total_time": f"{total_time:.2f} seconds",
        "urls_processed": urls,
    }

    print(f"Total time taken: {total_time:.2f} seconds")
    return result_summary
