import requests
import json
import os

# Calcula la ruta relativa a partir de utils.py
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
json_path = os.path.join(base_dir, 'home', 'static', 'preexistencias.json')
homologacion_path = os.path.join(base_dir, 'home', 'static', 'homologacion.xlsx')

def actualizar_token_wise():
    """Obtiene un nuevo token desde la API y lo guarda."""
    url_token = 'https://api.wcx.cloud/core/v1/authenticate'
    query_params = {'user': 'apinobis'}
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': 'be9dd08a9cd8422a9af1372a445ec8e4',
    }
    try:
        response = requests.get(url_token, headers=headers, params=query_params)
        response.raise_for_status()  # Lanza un error si la solicitud falla
       
        # Imprimir la respuesta completa para verificar la estructura
        #print(f"Respuesta de la API: {response.text}")
       
        # Suponiendo que el token está en la clave 'token'
        response_json = response.json()
        token = response_json.get('token', None)
       
        if token:
            #print(f"Nuevo token obtenido y guardado: {token}")
            return token
        else:
            raise Exception("No se encontró el token en la respuesta.")
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener el token: {e}")
 
 
def actualizar_token_gecros():
    url = "https://appmobile.nobissalud.com.ar/connect/token"
    payload = {
        'userName': '2|24588999',
        'password': 'wiseapi',
        'grant_type': 'password',
        'client_id': 'gecrosAppAfiliado'
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    try:
        response = requests.post(url, data=payload,headers=headers)
        response.raise_for_status()  # Lanza un error si la solicitud falla
       
        # Imprimir la respuesta completa para verificar la estructura
        #print(f"Respuesta de la API: {response.text}")
       
        # Suponiendo que el token está en la clave 'access_token'
        response_json = response.json()
        token = response_json.get('access_token', None)
       
        if token:
            #print(f"Nuevo token obtenido y guardado: {token}")
            return token
        else:
            raise Exception("No se encontró el token en la respuesta.")
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener el token: {e}")
        return None
    

def actualizar_preexistencias():
    url = "https://cotizador.nobis.com.ar/api/preex"
    headers = {
        "Content-Type": "application/json",
        'Authorization': 'Bearer 496ae7b9-0787-482e-bbe2-235279237940'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        response_json = response.json()

        if response_json:
            # Obtén la clave dinámica
            dynamic_key = next(iter(response_json.keys()))
            data_to_save = response_json[dynamic_key]

            # Guarda los datos en un archivo JSON
            with open(json_path, 'w', encoding='utf-8') as json_file:
                json.dump(data_to_save, json_file, ensure_ascii=False, indent=4)

            print("Datos guardados en 'preexistencias.json'")
        else:
            raise Exception("No hay datos de preexistencias.")

    except requests.exceptions.RequestException as e:
        print(f"Error al renovar preexistencias: {e}")
        return None

import unicodedata
# Función para normalizar texto (remover acentos)
def normalizar_texto(texto):
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("utf-8")
    return texto


# Función para buscar coincidencias parciales en el archivo JSON
def buscar_cobertura(coberturas):
    with open(json_path, "r", encoding="utf-8") as file:
        preexistencias = json.load(file)

    resultados = []
    lista_coberturas = [c.strip().upper() for c in coberturas.split(",")]

    for cobertura in lista_coberturas:
        for registro in preexistencias:
            patologia = registro["Patologia"].upper()
            patologia = normalizar_texto(patologia)

            # Limpieza de la cobertura buscada
            cobertura_limpia = normalizar_texto(cobertura.replace("  ", "").replace(" B", "").replace("FALSEO","").replace("- ","").replace("-","").replace("NO USAR","").replace("_",""))

            if cobertura_limpia in patologia:
                #print(f"Coincidencia para '{cobertura}':", registro)
                resultados.append(registro)

    return resultados


# Filtrar condición del grupo familiar
def condicion_grupal(convenio):
    if convenio:
        #print("Entrante " + convenio)
        if 'PREPAGO' in convenio.upper() or 'CLIENTE PP' in convenio.upper():
            #print("Prepago")
            return "3"
        elif 'MONOTRIBUTO' in convenio.upper() or 'CLIENTE MO' in convenio.upper():
            #print("MO")
            return "2"
        else:
            #print("RD")
            return "1" # Relacion de dependencia
    #print(convenio)
    return "1"

import pandas as pd

def buscar_preexistencias(ids_gecros):
    # Cargar el archivo de homologación
    df_homologacion = pd.read_excel(homologacion_path)
    
    # Convertir la entrada de IDs de Gecros en una lista
    lista_ids_gecros = [int(id.strip()) for id in ids_gecros.split(",") if id.strip().isdigit()]

    # Cargar el archivo JSON de preexistencias
    with open(json_path, "r", encoding="utf-8") as f:
        preexistencias = json.load(f)

    resultados = []

    for id_gecros in lista_ids_gecros:
        # Filtrar las filas que coinciden con el ID de Gecros
        filas = df_homologacion[df_homologacion.iloc[:, 0] == id_gecros]

        if filas.empty:
            continue  # Si no hay coincidencia, pasa al siguiente ID de Gecros
        
        for _, fila in filas.iterrows():
            # Obtener los IDs de cobertura especial y dividirlos en una lista
            ids_preexistencias = str(fila.iloc[2]).split(",")  # Asume que la 3ra columna contiene los IDs separados por coma
            ids_preexistencias = [int(id.strip()) for id in ids_preexistencias if id.strip().isdigit()]  # Limpiar y convertir

            # Buscar coincidencias en el JSON
            coincidencias = [p for p in preexistencias if p["ID"] in ids_preexistencias]

            resultados.extend(coincidencias)  # Agregar los resultados encontrados

    return resultados if resultados else "No se encontraron coincidencias."