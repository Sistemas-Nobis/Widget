from django.views import View
from django.shortcuts import render
from datetime import datetime
import requests
import json
from pandas import json_normalize
from .utils import actualizar_token_wise, actualizar_token_gecros, actualizar_preexistencias, buscar_cobertura, condicion_grupal, buscar_preexistencias
from django.core.cache import cache
import pytz
from dateutil.relativedelta import relativedelta
from django.http import HttpResponseBadRequest
import os
 
class BuscarAfiliadoView(View):
    template_name = 'ate_produccion.html'
 
    def obtener_token_wise(self):
        """
        Obtener el token desde el caché o actualizarlo si no existe o ha expirado.
        """
        # Verifica si el token está en el caché
        token = cache.get('api_token')
 
        if token is None:
            # Si el token no está en el caché o ha expirado, actualizar el token
            token = actualizar_token_wise()
            # Almacenar el token en caché con un tiempo de expiración de 50 minutos
            cache.set('api_token', token, timeout=50 * 60)  # 50 minutos = 50 * 60 segundos
 
        return token
   
    def obtener_token_gecros(self):
        # Verifica si el token está en el caché
        token = cache.get('gecros_token')
 
        if token is None:
            # Si el token no está en el caché o ha expirado, actualizar el token
            token = actualizar_token_gecros()
            # Almacenar el token en caché con un tiempo de expiración
            cache.set('gecros_token', token, timeout=1296000)
 
        return token
 
    def get(self, request, dni=None, *args, **kwargs):

        # Validación de entrada de DNI
        if not dni:
            return HttpResponseBadRequest("Debe proporcionar un DNI.")
        elif len(dni) != 8:
            return render(request, self.template_name, {'error': 'Verifique el número de DNI, debe ser de 8 dígitos.'}, status=400)
        
        fecha_actual = datetime.now().strftime("%Y-%m-%d")
        #print(f"La fecha actual es {fecha_actual} y el DNI {dni}")
 
        url_afiliado = "https://appmobile.nobissalud.com.ar/api/afiliados/gestionAfiliados"
       
        payload_afiliado = {
            "numero": None,
            "apellido": None,
            "nombre": None,
            "dni": dni,
            "cuil": None,
            "fecha": fecha_actual,
            "incluirGrupoFam": True
        }
 
        payload_json_afiliado = json.dumps(payload_afiliado)
        token_gecros = self.obtener_token_gecros()
 
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token_gecros}"
            }
       
        # Solicitud a la API de afiliados
        response_afiliado = requests.post(url_afiliado, data=payload_json_afiliado, headers=headers)
        #print(response_afiliado.text)
 
        if response_afiliado.status_code == 200:
            data_afiliado = response_afiliado.json().get('data', [])
            if data_afiliado:
                df_afiliado = json_normalize(data_afiliado)
                df_selected = df_afiliado[["nombre", "nroAfi", "parentesco"]]
                df_selected.columns = ["Nombre", "DNI", "Parentesco"]

                dni_aux = 0
                # Solicitud a la API de deuda
                for x in data_afiliado:
                    if x.get("esTitular") == True:
                        dni_aux = x.get("nroAfi")
                        print(f"Titular detectado: {dni_aux}")
                        break
                    else:
                        pass
                
                total_deuda = 0
                if dni_aux != 0:
                    url_deuda = f"https://appmobile.nobissalud.com.ar/api/AgentesCuenta/Deuda/{dni_aux}"
                    response_deuda = requests.get(url_deuda, headers=headers)
                    data_deuda = response_deuda.json()

                    hoy = datetime.today()

                    if response_deuda.status_code == 200 and data_deuda != []:
                        for deuda in data_deuda:
                            fecven_dt = datetime.strptime(deuda.get("fecven"), "%d/%m/%Y")
                            if fecven_dt < hoy:
                                total_deuda = sum(float(item.get("monto", 0)) for item in data_deuda)
                                total_deuda = "SI" if total_deuda > 0 else "NO"
                                break
                            else:
                                total_deuda = "NO"
                    
                    elif response_deuda.status_code != 200:
                        total_deuda = "Sin dato"

                    else:
                        total_deuda = "NO"
                else:
                    print("GRUPO FAMILIAR SIN TITULAR, REVISAR!")
                    total_deuda = "Sin titular"
 
                df_selected = df_selected.copy()
                df_selected["Deuda"] = total_deuda
 
                # Ordenar por parentesco
                orden_parentesco = {"TITULAR": 1, "CONYUGE": 2, "HIJO/A": 3, "FAMILIAR A CARGO": 4}
                df_selected["Parentesco_Orden"] = df_selected["Parentesco"].map(orden_parentesco)
                df_selected = df_selected.sort_values(by=["Parentesco_Orden"]).drop("Parentesco_Orden", axis=1)
                data = df_selected.to_dict(orient="records")
               
                # Obtener el token desde el caché o actualizarlo si ha expirado
                token = self.obtener_token_wise()
 
                # Solicitud a la API de casos
                headers_wise = headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token}',
                'x-api-key': 'be9dd08a9cd8422a9af1372a445ec8e4'
                }
 
                all_cases = []
 
                zona_horaria = pytz.timezone('America/Argentina/Buenos_Aires')
               
                # Fecha actual
                fecha_actual = datetime.now(zona_horaria)
 
                # Restar 3 meses a la fecha actual
                tres_meses_antes = fecha_actual - relativedelta(months=3)
 
                for afiliado in data_afiliado:
                    nro_afi = afiliado.get("nroAfi")
                    nom_afi = afiliado.get("nombre")
 
                    url_contacto = f'https://api.wcx.cloud/core/v1/contacts/?filtering=[{{"field":"contacts.personal_id","operator":"EQUAL","value":"{nro_afi}"}}]&fields=id,personal_id&sort=desc&sort_field=id&limit=5&page=1'
 
                    response_contacto = requests.request("GET", url_contacto, headers=headers_wise)
 
                    # Convertir la respuesta a un diccionario de Python
                    data_contacto = response_contacto.json()
 
                    # Acceder a uno de los datos, por ejemplo, el valor del campo 'id'
                    if 'data' in data_contacto and len(data_contacto['data']) > 0:
                        first_item = data_contacto['data'][0]  # Primer elemento de la lista de resultados
                        contact_id = first_item.get('id')
                        print(f"Contacto_ID: {contact_id}")
 
                        # Consulta de casos
                        url_casos = f'https://api.wcx.cloud/core/v1/cases?sort=asc&sort_field=last_update&limit=10&page=1&filtering=[{{"field":"case.contact_id","operator":"EQUAL","value":"{contact_id}"}}]&fields=id,number,user_id,status,created_at,user_id,source_channel,type_id,tags,channel_account'
                        response_casos = requests.get(url_casos, headers=headers_wise)
 
                        if response_casos.status_code == 200:
                            data_casos = response_casos.json().get('data', [])
 
                            # Crear un diccionario para almacenar los nombres de usuarios por user_id
                            user_names = {}
                            type_names = {}
 
                            for caso in data_casos:
                                user_id = caso.get('user_id')
                                type_id = caso.get('type_id')
 
                                caso['channel_account'] = nom_afi
 
                                fecha_str = caso.get('created_at')
                                if fecha_str:
                                    # Convertir y reformatear la fecha
                                    fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d %H:%M:%S')
 
                                    # Formato corto: solo día y mes
                                    caso['created_at'] = fecha_obj.strftime('%d-%m')
 
                                    # Formato largo: dia, mes, hora y minutos
                                    caso['created_at_full'] = fecha_obj.strftime('%d-%m | %H:%M')
                                else:
                                    caso['created_at'] = "Fecha no disponible"
                                    caso['created_at_full'] = "Fecha no disponible"
                               
                                # Traducción de estados.
                                status_str = caso.get('status')
                                if status_str:
                                    if caso['status'].lower() == 'closed':
                                        caso['status'] = 'Cerrado'
                                    elif caso['status'].lower() == 'open':
                                        caso['status'] = 'Abierto'
                                    elif caso['status'].lower() == 'onhold':
                                        caso['status'] = 'Espera'
                                    elif caso['status'].lower() == 'solved':
                                        caso['status'] = 'Resuelto'
                                    elif caso['status'].lower() == 'pending':
                                        caso['status'] = 'Pendiente'
                                    else:
                                        pass
 
                                # Usuario/Asesor
                                if user_id not in user_names:
                                    # Realizar solicitud a la API para obtener el nombre del usuario
                                    url_usuario = f'https://api.wcx.cloud/core/v1/users?filtering=[{{"field":"users.id","operator":"EQUAL","value":"{user_id}"}}]&fields=nick,id'
                                    response_usuario = requests.get(url_usuario, headers=headers_wise)
 
                                    data_user = response_usuario.json()
 
                                    if response_usuario.status_code == 200:
                                        if 'data' in data_user and len(data_user['data']) > 0:
                                            first_item = data_user['data'][0]  # Primer elemento de la lista de resultados
                                            contact_id = first_item.get('id')
                                            contact_nom = first_item.get('nick')
 
                                            # Reemplazar user_id con el nombre del usuario en la data de casos
                                            caso['user_id'] = contact_nom if user_id == contact_id else "Nombre no disponible"
                                        else:
                                            print("No se encontraron datos del nombre de usuario.")
 
                                    elif response_usuario.status_code == 400:
                                        caso['user_id'] = 'Sin asesor'
 
                                    else:
                                        user_names[user_id] = 'N/A'
 
                                # Tipos
                                if type_id not in type_names:
                                    url_tipos = f'https://api.wcx.cloud/core/v1/cases/types?filtering=[{{"field":"types.id","operator":"EQUAL","value":"{type_id}"}}]&fields=id,name'
                                    response_tipos = requests.get(url_tipos, headers=headers_wise)
 
                                    data_tipos = response_tipos.json()
 
                                    if response_tipos.status_code == 200:
                                        if 'data' in data_tipos and len(data_tipos['data']) > 0:
                                            first_item = data_tipos['data'][0]  # Primer elemento de la lista de resultados
                                            tipo_id = first_item.get('id')
                                            tipo_nom = first_item.get('name')
 
                                            # Reemplazar user_id con el nombre del tipos en la data de casos
                                            caso['type_id'] = tipo_nom if type_id == tipo_id else "Tipo no disponible"
                                        else:
                                            print("No se encontraron datos del nombre de tipos.")
 
                                    elif response_tipos.status_code == 400:
                                        caso['type_id'] = 'Sin tipo'
 
                                    else:
                                        type_names[type_id] = 'N/A'
                               
                                # Convertir fecha_obj a timezone-aware
                                fecha_obj = zona_horaria.localize(fecha_obj)
 
                                # Comparar fechas
                                if tres_meses_antes <= fecha_obj <= fecha_actual:
                                    #print("Fecha OK.")
                                    # Añadir el caso reformateado a la lista
                                    all_cases.append(caso)
                                else:
                                    pass
                                    #print("Fecha INVALIDA.")
 
                        else:
                            pass
                       
                        # Ordenar los casos por la fecha 'created_at'
                        all_cases = sorted(all_cases, key=lambda x: datetime.strptime(x['created_at_full'], '%d-%m | %H:%M'), reverse=True)
 
                    else:
                        print(f"No se encontraron datos de contacto para {nro_afi}.")
 
                # Renderiza la plantilla con ambos conjuntos de datos
                return render(request, self.template_name, {'data': data, 'data_casos': all_cases})
 
            else:
                return render(request, self.template_name, {'error': 'No se encontraron datos para el DNI proporcionado.'}, status=404)
       
        elif response_afiliado.status_code == 400:
            return render(request, self.template_name, {'error': f'El servidor retornó un error 400. Comprueba los parámetros de la solicitud.'}, status=400)
       
        else:
            return render(request, self.template_name, {'error': f'Error en la solicitud. Código de estado: {response_afiliado.status_code}'}, status=500)
       
from django.shortcuts import render
from django.utils.safestring import mark_safe

class BuscarRetencionView(View):
    template_name = 'rete_produccion.html'
 
    def obtener_token_wise(self):
        """
        Obtener el token desde el caché o actualizarlo si no existe o ha expirado.
        """
        # Verifica si el token está en el caché
        token = cache.get('api_token')
 
        if token is None:
            # Si el token no está en el caché o ha expirado, actualizar el token
            token = actualizar_token_wise()
            # Almacenar el token en caché con un tiempo de expiración de 50 minutos
            cache.set('api_token', token, timeout=50 * 60)  # 50 minutos = 50 * 60 segundos
 
        return token
   
    def obtener_token_gecros(self):
        # Verifica si el token está en el caché
        token = cache.get('gecros_token')
 
        if token is None:
            # Si el token no está en el caché o ha expirado, actualizar el token
            token = actualizar_token_gecros()
            # Almacenar el token en caché con un tiempo de expiración
            cache.set('gecros_token', token, timeout=1296000)
 
        return token

    def obtener_preex(self):
        # Endpoint y configuración
        url_api = "https://cotizador.nobis.com.ar/api/preex"
        headers = {
            "Content-Type": "application/json",
            'Authorization': 'Bearer 496ae7b9-0787-482e-bbe2-235279237940'
        }

        # Obtener la clave dinámica almacenada en caché
        clave_dinamica_cache = cache.get('clave_dinamica_preex')
        verificacion_diaria = cache.get('verificacion_diaria_preex')

        # Si no se realizó la verificación diaria
        if not verificacion_diaria:
            try:
                # Obtener la clave dinámica actual desde la API
                response = requests.get(url_api, headers=headers)
                response.raise_for_status()
                response_json = response.json()
                clave_dinamica_actual = next(iter(response_json.keys()))

                # Si no hay clave almacenada o si cambió, actualizar el archivo
                if clave_dinamica_cache != clave_dinamica_actual:
                    print("La clave dinámica ha cambiado. Actualizando archivo...")
                    actualizar_preexistencias()
                    cache.set('clave_dinamica_preex', clave_dinamica_actual, timeout=30 * 24 * 3600)  # 30 días

                # Registrar que se realizó la verificación diaria
                cache.set('verificacion_diaria_preex', True, timeout=24 * 3600)  # 24 horas

            except requests.exceptions.RequestException as e:
                print(f"Error al consultar la clave dinámica: {e}")
                return None

        # Ruta absoluta al archivo preexistencias.json
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        json_path = os.path.join(base_dir, 'home', 'static', 'preexistencias.json')

        # Leer y devolver el contenido del archivo actualizad
        try:
           with open(json_path, 'r', encoding='utf-8') as archivo:
              return json.load(archivo)
        except FileNotFoundError:
           print("Archivo local no encontrado. Ejecutando actualización...")
           actualizar_preexistencias()
           with open(json_path, 'r', encoding='utf-8') as archivo:
              return json.load(archivo)

 
    def get(self, request, dni=None, *args, **kwargs):

        self.obtener_preex() # Verificar lista de patologias

        # Validación de entrada de DNI
        if not dni:
            return HttpResponseBadRequest("Debe proporcionar un DNI.")
        elif len(dni) != 8:
            return render(request, self.template_name, {'error': 'Verifique el número de DNI, debe ser de 8 dígitos.'}, status=400)

        fecha_actual = datetime.now().strftime("%Y-%m-%d")
        #print(f"La fecha actual es {fecha_actual} y el DNI {dni}")
 
        url_afiliado = "https://appmobile.nobissalud.com.ar/api/afiliados/gestionAfiliados"
       
        payload_afiliado = {
            "numero": None,
            "apellido": None,
            "nombre": None,
            "dni": dni,
            "cuil": None,
            "fecha": fecha_actual,
            "incluirGrupoFam": True
        }
 
        payload_json_afiliado = json.dumps(payload_afiliado)
        token_gecros = self.obtener_token_gecros()
 
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token_gecros}"
            }
        
        headers_interno = {
            "Content-Type": "application/json"
            }
       
        # Solicitud a la API de afiliados
        response_afiliado = requests.post(url_afiliado, data=payload_json_afiliado, headers=headers)
        #print(response_afiliado.text)
 
        if response_afiliado.status_code == 200:
            data_afiliado = response_afiliado.json().get('data', [])
            if data_afiliado:
                df_afiliado = json_normalize(data_afiliado)
                #print(df_afiliado)
                df_selected = df_afiliado[["nombre", "nroAfi", "parentesco", "estadoBenef", "benGrId", "convenio.value"]]
                df_selected.columns = ["Nombre", "DNI", "Parentesco", "Estado", "Grupo", "Condicion"]

                # Crear lista de resultados combinados
                resultados_combinados = []

                # Crear lista de resultado bonificacion y forma de pago
                forma_de_pago_bonif = []

                grupo = data_afiliado[0].get("benGrId")

                convenio_id = "1"
                convenio_entry = df_afiliado.iloc[0]["convenio.value"] # Tomar convenio de Gecros
                
                url_dniage = f"https://api.nobis.com.ar/dni_agecta/{grupo}"
                response_dniage = requests.get(url_dniage, headers=headers_interno)
                dni_aux = 0

                if response_dniage.status_code == 200:
                    data_dniage = response_dniage.json()

                    dni_aux = data_dniage[0].get("doc_id") #DNI de agente de cuenta

                else:
                    print("No hay dni de agente de cuenta.")

                hoy = datetime.today()

                if dni_aux != 0:
                    url_deuda = f"https://appmobile.nobissalud.com.ar/api/AgentesCuenta/Deuda/{dni_aux}"
                    response_deuda = requests.get(url_deuda, headers=headers)
                    if response_deuda.status_code == 200:
                        data_deuda = response_deuda.json()
                        total_deuda = 0
                        for deuda in data_deuda:
                            fecvenc_dt = datetime.strptime(deuda.get("fecven"), "%d/%m/%Y")
                            if fecvenc_dt < hoy:
                                total_deuda += float(deuda.get("monto"))
                            else:
                                pass
                        total_deuda = total_deuda if total_deuda > 0 else "Sin deuda"
                    else:
                        total_deuda = "Sin dato"
                    
                    # Forma de pago y Bonificacion/Recargo
                    url_bf = f"https://api.nobis.com.ar/fpago_bonif/{dni_aux}"
                    response_bf = requests.get(url_bf, headers=headers_interno)

                    if response_bf.status_code == 200:
                        data_bf = response_bf.json()

                        if data_bf:

                            fpago = data_bf[0].get("fpago_nombre").replace("  ","")
                            #print(fpago)
                            data_bf[0]["fpago_nombre"] = fpago
                            #print(data_bf[0]["fpago_nombre"])

                            # Bonificacion / Recargo
                            porcentaje = data_bf[0].get("porcentaje")
                            if porcentaje is not None:
                                #print(porcentaje)
                                porcentaje = f"{porcentaje / 100:.0%}"
                                #print(porcentaje.replace("-",""))
                                data_bf[0]["porcentaje"] = porcentaje

                                periodo_hasta = data_bf[0].get("peri_hasta")
                                #print(periodo_hasta)
                                periodo_hasta = datetime.strptime(periodo_hasta, '%Y%m') # Formato en el que viene el dato
                                periodo_hasta_format = periodo_hasta.strftime("%m/%Y") # Formato a mostrar
                                #print(periodo_hasta_format)
                                data_bf[0]["peri_hasta"] = periodo_hasta_format

                                # Detalles
                                if data_bf[0]["rg_id"] is not None:
                                    data_bf[0]["BonficaRec_obs"] = data_bf[0]["rg_nombre"]
                                elif data_bf[0]["BonficaRec_obs"] is None:
                                    data_bf[0]["BonficaRec_obs"] = "Manual - Sin observación"
                                else:
                                    pass

                            else:
                                data_bf[0]["peri_hasta"] = 0

                            forma_de_pago_bonif.append(data_bf[0])
                            #print(data_bf[0])
                        else:
                            print("La API devolvió una lista vacía.")
                    else:
                        pass

                else:
                    print("GRUPO FAMILIAR SIN TITULAR, REVISAR!")
                    total_deuda = "Sin titular"

                # DESARROLLAR INFO FALTANTE
                cobertura = 0

                for afiliado in data_afiliado:
                    nro_afi = afiliado.get("nroAfi")
                    afiliado_info = {
                        "Nombre": afiliado.get("nombre"),
                        "DNI": nro_afi,
                        "Parentesco": afiliado.get("parentesco"),
                        "Estado": afiliado.get("estadoBenef"),
                        "Deuda": total_deuda,
                        "Patologias": []
                    }

                    if 'con' in afiliado_info["Estado"].lower():
                        #print(f"Con cobertura: {afiliado_info["DNI"]}")

                        cobertura += 1
 
                        if 'TITULAR' in afiliado.get("parentesco"):
                            # Tomar tipo de beneficiario del titular
                            url_tipoben = f"https://api.nobis.com.ar/tipo_ben/{nro_afi}"
                            response_tipoben = requests.get(url_tipoben, headers=headers_interno)

                            if response_tipoben.status_code == 200:
                                data_tipoben = response_tipoben.json()
                                #print(nro_afi)

                                tipo_beneficiario = data_tipoben[0].get("tipoBen_nom") #DNI de agente de cuenta
                                #print(f"Tipo afi: {tipo_beneficiario}")

                                convenio_id = condicion_grupal(tipo_beneficiario) # Reevaluar convenio y matchear con el ID del html

                            else:
                                #print("No hay dni de agente de cuenta.")
                                pass
                            
                        else:
                            pass

                        # Solicitud a la API de afiliados para obtener edad y provincia
                        url_afiliado_extra = f"https://appmobile.nobissalud.com.ar/api/afiliados?numero={nro_afi}"
                        response_afiliado_extra = requests.get(url_afiliado_extra, headers=headers)
                        data_afiliado_extra = response_afiliado_extra.json().get('data', [])
    
                        if data_afiliado_extra:
                            fecha_nacimiento = data_afiliado_extra[0].get('fechaNacimiento')
                            df_afiliado_extra = json_normalize(data_afiliado_extra, record_path=['domicilios'], meta=['benId', 'nombreAfiliado', 'fechaNacimiento'])
                        
                            # Provincia
                            if 'provincia' in df_afiliado_extra.columns:
                                provincia = df_afiliado_extra['provincia'].iloc[0]
                                afiliado_info['Provincia'] = provincia
                            else:
                                afiliado_info['Provincia'] = 'Sin provincia'
    
                            # Calcular edad
                            if fecha_nacimiento:
                                fecha_nacimiento_dt = datetime.strptime(fecha_nacimiento, "%d/%m/%Y")
                                hoy = datetime.today()
                                edad = hoy.year - fecha_nacimiento_dt.year - ((hoy.month, hoy.day) < (fecha_nacimiento_dt.month, fecha_nacimiento_dt.day))
                                afiliado_info['Edad'] = edad
                            else:
                                afiliado_info['Edad'] = "Sin fecha de nacimiento"

                        # Solicitud a la API interna para obtener fecha de alta y patologia
                        url_patologias = f"https://api.nobis.com.ar/fecha_alta_y_patologias/{nro_afi}"
                        response_p = requests.get(url_patologias, headers=headers_interno)
                        data_p = response_p.json()

                        if data_p:
                            
                            # Fecha de alta
                            fecha_alta = data_p[0].get('fecha_alta')
                            fecha_alta_format = datetime.strptime(fecha_alta, '%Y-%m-%dT%H:%M:%S.000')

                            fecha_formateada = fecha_alta_format.strftime('%d-%m-%Y')

                            afiliado_info['Fecha_alta'] = fecha_formateada

                            patologia = data_p[0].get('cobertura_especial')
                            patologias_id = data_p[0].get('id_cobertura_especial')
                            
                            if patologia != None:
                                #print(patologia)
                                busqueda = buscar_cobertura(patologia)
                                #print(busqueda)
                                if busqueda == []:
                                    #print(f"Segunda busqueda: {patologias_id}")
                                    busqueda = buscar_preexistencias(patologias_id)
                                    #print(busqueda)
                                
                                afiliado_info['Patologias'] = busqueda
                                afiliado_info['Cobertura_especial'] = patologia
                                #print("Encontrado.")
                            else:
                                afiliado_info['Cobertura_especial'] = 'Sin cobertura especial'
                                #print("SIN COBERTURA ESPECIAL")
                        else:
                            print("Error. Fecha de alta no encontrada.")

                        resultados_combinados.append(afiliado_info)
                    else:
                        #print(f"Afiliado sin cobertura: {afiliado_info["DNI"]}")
                        pass
                
                if cobertura == 0:
                    print("⚠️ No hay afiliados con cobertura dentro del grupo familiar ⚠️")

                # Aportes
                all_aportes = []

                url_aportes = f"https://api.nobis.com.ar/ultimos_aportes/{dni_aux}"
                response_a = requests.get(url_aportes, headers=headers_interno)
                data_a = response_a.json()

                cont = 0

                if data_a:
                    for aporte in data_a:
                        if cont != 5:
                            # Supongamos que `periodo` es una cadena como '202410'
                            periodo = aporte.get('Periodo')

                            # Convertir el período a un objeto datetime
                            fecha = datetime.strptime(periodo, '%Y%m')

                            # Sumar 3 meses usando relativedelta
                            nueva_fecha = fecha + relativedelta(months=3)

                            # Convertir de nuevo a formato 'YYYYMM'
                            nuevo_periodo = nueva_fecha.strftime('%Y%m')

                            aporte['Periodo'] = nuevo_periodo

                            monto = aporte.get('aporte')
                            #print(monto)

                            #dni = aporte.get('numero').replace(' ', '')
                            #aporte['numero'] == dni
                            #print(dni)

                            if monto > 1:
                                all_aportes.append(aporte)
                                cont+=1
                            else:
                                pass
                        else:
                            break
                else:
                    pass

                # Ordenar por parentesco
                orden_parentesco = {"TITULAR": 1, "CONYUGE": 2, "HIJO/A": 3, "FAMILIAR A CARGO": 4}
                for afiliado in resultados_combinados:
                    afiliado['Parentesco_Orden'] = orden_parentesco.get(afiliado['Parentesco'], 99)  # 99 para no asignar un orden conocido
 
                resultados_combinados.sort(key=lambda x: x['Parentesco_Orden'])
                for afiliado in resultados_combinados:
                    del afiliado['Parentesco_Orden']  # Eliminar el campo de ordenamiento antes de renderizar
                
                #print(resultados_combinados)

                # Renderiza la plantilla con ambos conjuntos de datos
                return render(request, self.template_name, {'data': resultados_combinados, 'data_aportes': all_aportes, 'data_fpago': forma_de_pago_bonif, "convenio_id": convenio_id, "convenio_nom":convenio_entry, "tipo_nom":tipo_beneficiario})
            
            else:
                return render(request, self.template_name, {'error': 'No se encontraron datos para el DNI proporcionado.'}, status=404)
            
        elif response_afiliado.status_code == 400:
            return render(request, self.template_name, {'error': f'El servidor retornó un error 400. Comprueba los parámetros de la solicitud.'}, status=400)
       
        else:
            return render(request, self.template_name, {'error': f'Error en la solicitud. Código de estado: {response_afiliado.status_code}'}, status=500)
        

# COTIZADOR

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def cotizar_actual(request):
    if request.method == 'POST':
        # Leer datos enviados desde el frontend
        data = json.loads(request.body)
        mes = data.get('mes')
        plan = data.get('plan')
        gestion = data.get('gestion')
        ubicacion = data.get('ubicacion')
        aporte = data.get('aportes')
        bonificacion = data.get('bonificaciones')
        patologias = data.get('patologias')
        edades = ','.join(data.get('edades', []))  # Convertir lista de edades en cadena separada por comas

        # Verificar si todos los parámetros necesarios están presentes
        if not all([mes, plan, gestion, ubicacion, edades]):
            return JsonResponse({"error": "Faltan parámetros"}, status=400)
        
        #print("Datos recibidos:", data)

        # Token fijo
        token = "496ae7b9-0787-482e-bbe2-235279237940"

        # Construir URL de la API externa
        url_api = f"https://cotizador.nobis.com.ar/api?mes={mes}&planes={plan}&gestion={gestion}&ubicacion={ubicacion}&ages={edades}&directo={aporte}&descuento={bonificacion}&preexistencia={patologias}"

        # Consultar la API externa
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
                }

            response = requests.get(url_api, headers=headers)
            response_data = response.json()

            # Extraer los valores necesarios
            valor_pc = response_data['resultado']['cotizacion']['planes'][0]['primera_cuota']
            valor_p = response_data['resultado']['cotizacion']['planes'][0]['valor_plan']

            # Enviar respuesta al frontend
            return JsonResponse({
                "primera_cuota": valor_pc,
                "valor_plan": valor_p
            })
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Método no permitido"}, status=405)