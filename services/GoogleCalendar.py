import os.path
import datetime as dt
import json
from typing import List
import requests
import pickle
from urllib.parse import quote
import urllib.parse

from datetime import datetime, timezone, timedelta, time
import sys
from googleapiclient.discovery import build

#from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES =[ "https://www.googleapis.com/auth/calendar", 'https://www.googleapis.com/auth/calendar.readonly']

class GoogleCalendarManager:
    def __init__(self):
        self.service = self._authenticate()
        
    def _authenticate(self):
        """
        Maneja la autenticación con Google Calendar mediante OAuth.
        Las credenciales se obtienen de una variable de entorno (JSON).
        Si existe un token pickle válido, se usa en vez de pedir autorización.
        Devuelve el servicio de Calendar construido con las credenciales.
        """
        creds = None
        token_file = 'token.pickle'  # Archivo donde se almacenará el token

        # 1. Revisa si existe un token previo en token.pickle
        if os.path.exists(token_file):
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)

        # 2. Si no hay token o no es válido, hay que generar uno nuevo o refrescarlo
        if not creds or not creds.valid:
            # Si el token existe pero está expirado y tiene refresh_token, se refresca
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Lee las credenciales de la variable de entorno
                credentials_json = os.getenv('CALENDAR_CREDENTIALS')
                if not credentials_json:
                    raise EnvironmentError(
                        "La variable de entorno 'CALENDAR_CREDENTIALS' no está configurada."
                    )

                # Convierte el contenido de la variable de entorno a diccionario
                client_config = json.loads(credentials_json)
                print(credentials_json)
                print(client_config)
                # Usa InstalledAppFlow para manejar la autenticación OAuth local
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                creds = flow.run_local_server(port=8080)

            # Guarda el token para uso futuro
            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)

        # 3. Construye el servicio de la API de Google Calendar y devuélvelo
        return build("calendar", "v3", credentials=creds)
    



    def list_events(
        self, 
        client_name,
        phone, 
        date=None, 
        time=None, 
        event_title=None,
        days_ahead=5, 
        max_results=10
    ):

        calendar_id = "adb251c8302274d034db57f0027fbba2e4b04b00d19f3e2079761042d7e60ac5@group.calendar.google.com"

        # 1. Construimos timeMin y timeMax en función de date y time
        if date:
            # Si hay una fecha provista, la parseamos
            try:
                date_dt = dt.datetime.strptime(date, '%Y-%m-%d').date()
            except ValueError:
                print("El parámetro 'date' debe estar en formato YYYY-MM-DD.")
                return []

            if time:
                # Si además hay una hora provista, la parseamos
                try:
                    time_dt = dt.datetime.strptime(time, '%H:%M').time()
                except ValueError:
                    print("El parámetro 'time' debe estar en formato HH:MM.")
                    return []
                start_dt = dt.datetime.combine(date_dt, time_dt)
            else:
                # Si no hay hora, asumimos 00:00:00 en la fecha dada
                start_dt = dt.datetime.combine(date_dt, dt.time(0, 0, 0))

            # timeMin inicia en start_dt
            time_min = start_dt.replace(microsecond=0).isoformat() + "Z"
            # timeMax se va a "days_ahead" días desde start_dt, terminado a las 23:59:59
            time_max = (
                start_dt + dt.timedelta(days=days_ahead)
            ).replace(hour=23, minute=59, second=59, microsecond=0).isoformat() + "Z"
        else:
            # Si no se ha provisto fecha, consultamos desde "ahora"
            now = dt.datetime.now().replace(microsecond=0)
            time_min = now.isoformat() + "Z"
            time_max = (
                now + dt.timedelta(days=days_ahead)
            ).replace(hour=23, minute=59, second=59, microsecond=0).isoformat() + "Z"

        # 2. Construimos los parámetros para la llamada a la API
        query_params = {
            'calendarId': calendar_id,
            'timeMin': time_min,
            'timeMax': time_max,
            'maxResults': max_results,
            'singleEvents': True,
            'orderBy': 'startTime'
        }

        # Si se indicó un título, usamos el parámetro 'q' para hacer la búsqueda textual
        if event_title:
            query_params['q'] = event_title

        # 3. Llamada a la API (manejo de excepciones)
        try:
            events_result = self.service.events().list(**query_params).execute()
        except Exception as e:
            print(f"Error consultando la API de Google Calendar: {str(e)}")
            return []
        
        events = events_result.get('items', [])

        # 4. Mostrar resultados
        if not events:
            print('No se encontraron eventos con los criterios proporcionados.')
        else:
            for event in events:
                summary = event.get('summary', 'Sin título')
                event_id = event.get('id', 'Sin ID')
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                print(f"El evento '{summary}' comienza en {start} y termina en {end}. ID: {event_id}")

        return events
    
    def list_calendars(self):
        """
        Obtiene y muestra una lista de los calendarios a los que 
        tiene acceso el usuario autenticado.
        """
        try:
            calendars_result = self.service.calendarList().list().execute()
            calendars = calendars_result.get('items', [])
            for cal in calendars:
                print(f"Calendar: {cal['summary']} - ID: {cal['id']}")
            return calendars
        except Exception as e:
            print(f"Error al listar los calendarios: {e}")
            return []
            
    def delete_record(self, record_id):
        """
        Elimina un registro existente en Airtable.

        Args:
            record_id (str): ID del registro a eliminar.

        Returns:
            bool: True si el registro se eliminó correctamente, False en caso de error.
        """
        # Validar entrada
        if not record_id:
            raise ValueError("Se requiere el ID del registro para eliminarlo.")

        # Construir la URL para el registro específico
        url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}/{record_id}"

        try:
            # Enviar la solicitud DELETE para eliminar el registro
            response = requests.delete(url, headers=self.headers)
            response.raise_for_status()
            print("Registro eliminado exitosamente de Airtable.")
            return True
        except requests.exceptions.RequestException as e:
            print("Error al eliminar el registro en Airtable.")
            print("Detalles del error:", e)
            print("Respuesta del servidor:", response.text if response else "No hay respuesta.")
            return False

    def create_google_calendar_event(self, client_name, service, start_time, email, phone, event_title, event_body):
        print("Consulta de eventos")

        # Aquí debería ir una función para comprobar la disponibilidad de la cita
        print("Procesamos creación de evento")
        start_time_dt = datetime.fromisoformat(start_time)
        end_time_dt = start_time_dt + timedelta(hours=1)
        end_time = end_time_dt.isoformat()

        event = {
            'summary': event_title,
            'description': event_body,
            'start': {
                'dateTime': start_time,
                'timeZone': 'America/Mexico_City',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'America/Mexico_City',
            },
        }
        print(event)

        try:
            print("Procesamos creación de evento TRY")
            created_event = self.service.events().insert(
                calendarId='d259e3166fba78346e0ab55a19cec0f3813ae9f345aafcb3442d0bbfddd193d8@group.calendar.google.com', 
                body=event
            ).execute()

            # Preparar datos para Airtable
            event_data = {
                "client_name": client_name,
                "service": service,
                "start_time": start_time,
                "email": email,
                "phone": phone,
                "event_title": event_title,
                "event_body": event_body,
                "appointment_id": created_event.get("id"),
                "summary": created_event.get("summary"),
                "start_time_google": created_event['start'].get('dateTime'),
                "end_time_google": created_event['end'].get('dateTime'),
                "htmlLink": created_event.get('htmlLink')
            }

            # Registrar en Airtable
            self.register_event_in_airtable(event_data)

            return {
                "message": "La operación se completó exitosamente.",
                "data": event_data
            }

        except Exception as e:
            print(f"Error al crear evento: {str(e)}")
            raise

    def register_event_in_airtable(self, event_data):
        airtable_base_id = "appNoCdc4QUiSEEmj"
        airtable_api_key = "patzqXyEp3hvgvI1p.c843468d3874a2d8a96893736592497900ba99e1009d1901dfa2cc9cd79da1ba"
        table_name = "citas"
        url = f"https://api.airtable.com/v0/{airtable_base_id}/{table_name}"
        headers = {
            "Authorization": f"Bearer {airtable_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "fields": {
                "idCita": event_data.get("event_title"),
                "descripcionCita": event_data.get("event_body"),

            }
        }

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            print("Evento registrado exitosamente en Airtable.")
            return response.json()
        else:
            print(f"Error al registrar el evento en Airtable: {response.text}")
            response.raise_for_status()

    def update_google_calendar_event_by_details(self,creds, event_title, start_time, updated_title=None, updated_start=None, updated_end=None):
        service = build('calendar', 'v3', credentials=creds)

        try:
            start_datetime = datetime.fromisoformat(start_time)
            time_min = (start_datetime + timedelta(minutes=359)).isoformat() + "Z"
            time_max = (start_datetime + timedelta(minutes=361)).isoformat() + "Z"
            new_start_time = start_datetime.isoformat() + "-06:00"

            if updated_start:
                updated_start_datetime = datetime.fromisoformat(updated_start)
                updated_start = updated_start_datetime.isoformat()
            if updated_end:
                updated_end_datetime = datetime.fromisoformat(updated_end)
                updated_end = updated_end_datetime.isoformat()

            events = self.get_google_calendar_events(creds, time_min, time_max)

            for event in events:
                print(event['start']['dateTime'])
                print(new_start_time)
                if event['summary'] == event_title and event['start']['dateTime'] == new_start_time:
                    if updated_title:
                        event['summary'] = updated_title
                    if updated_start:
                        event['start']['dateTime'] = updated_start
                    if updated_end:
                        event['end']['dateTime'] = updated_end

                    updated_event = service.events().update(
                        calendarId='c_5429309c7c93803f3c31f144ef187db179ada2d6ad3d527aba230d3293704913@group.calendar.google.com',
                        eventId=event['id'],
                        body=event
                    ).execute()

                    print(f"Evento actualizado: {updated_event.get('htmlLink')}")
                    return updated_event

            return {"status": "not_found", "message": f"No se encontró un evento con el título '{event_title}' y la hora de inicio '{new_start_time}'."}

        except Exception as e:
            print(f"Error al actualizar el evento: {str(e)}")
            return {"status": "error", "message": str(e)}
        
    def get_appointments(self, user_name, service, future_only):
        """
        Obtiene la información de citas agendadas filtradas por usuario, servicio y tiempo.

        Args:
            user_name (str): Nombre del usuario para filtrar las citas.
            service (str): Nombre del servicio para filtrar las citas.
            future_only (bool): Indica si solo se deben devolver citas futuras.

        Returns:
            dict: Lista de citas filtradas o mensaje de error.
        """
        try:
            # Definir los rangos de tiempo para la búsqueda
            now = datetime.now(timezone.utc).isoformat()  # Tiempo actual en formato ISO 8601
            
            print("OBTENEMOS CITAS DEL USUARIO")
            
            # Obtener todas las citas desde Google Calendar
            events_result = self.service.events().list(
                calendarId='c_5429309c7c93803f3c31f144ef187db179ada2d6ad3d527aba230d3293704913@group.calendar.google.com',
                timeMin=now if future_only else None,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            if not events:
                return {
                    "message": "No se encontraron citas agendadas.",
                    "data": []
                }

            # Filtrar eventos basados en 'user_name' y 'service'
            filtered_events = []
            for event in events:
                summary = event.get('summary', '')
                description = event.get('description', '')
                start_time = event['start'].get('dateTime', event['start'].get('date'))
                end_time = event['end'].get('dateTime', event['end'].get('date'))

                # Aplicar filtros de usuario y servicio
                if user_name.lower() in summary.lower() and service.lower() in summary.lower():
                    filtered_events.append({
                        "appointment_id": event.get('id'),
                        "user_name": user_name,
                        "service": service,
                        "start_time": start_time,
                        "end_time": end_time,
                        "description": description,
                        "summary": summary,
                        "location": event.get('location', 'No se proporcionó una ubicación')
                    })
            
            print(filtered_events)

            if not filtered_events:
                return {
                    "message": "No se encontraron citas que coincidan con los filtros especificados.",
                    "data": []
                }

            return {
                "message": "La operación se completó exitosamente.",
                "data": filtered_events
            }

        except HttpError as error:
            print(f"Error al obtener las citas: {error}")
            return {
                "message": "Ocurrió un error al obtener las citas desde Google Calendar.",
                "error": str(error)
            }

        except Exception as e:
            print(f"Error inesperado: {str(e)}")
            return {
                "message": "Error inesperado al procesar la operación.",
                "error": str(e)
            }
    
    def cancel_appointment(self, client_name, phone, start_time, cancel_reason=None):
        calendarId= os.getenv("CALENDAR_ID")
        print("HOLA")
        print(calendarId)
        try:
            # Convertir start_time a objeto datetime
            appointment_time = datetime.fromisoformat(start_time)

            # Definir rangos de tiempo precisos con zona horaria explícita
            time_min = (appointment_time - timedelta(minutes=1)).isoformat()
            time_max = (appointment_time + timedelta(minutes=1)).isoformat()

            # Obtener los eventos en el rango de tiempo
            events_result = self.service.events().list(
                calendarId=calendarId,
                timeMin=f"{time_min}Z",
                timeMax=f"{time_max}Z",
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            # Filtrar el evento por el nombre o teléfono del cliente
            event_to_delete = None
            for event in events:
                summary = event.get('summary', '')
                start_time_event = event['start'].get('dateTime', '')

                if (client_name.lower() in summary.lower() or phone in summary) and start_time_event.startswith(start_time):
                    event_to_delete = event
                    break

            # Si no se encuentra el evento
            if not event_to_delete:
                return {
                    "message": "No se encontró ninguna cita que coincida con los criterios especificados.",
                    "status": "not_found",
                    "data": []
                }

            # Eliminar el evento encontrado
            self.service.events().delete(
                calendarId=calendarId,
                eventId=event_to_delete['id']
            ).execute()

            # Log de la razón de cancelación
            print(f"Cita cancelada. Razón: {cancel_reason}" if cancel_reason else "Cita cancelada sin razón especificada.")

            # Devolver respuesta estandarizada
            return {
                "message": "La cita ha sido cancelada exitosamente.",
                "status": "success",
                "data": {
                    "appointment_id": event_to_delete['id'],
                    "client_name": client_name,
                    "phone": phone,
                    "start_time": start_time,
                    "cancel_reason": cancel_reason if cancel_reason else "No especificada",
                    "summary": event_to_delete.get('summary', ''),
                    "status": "cancelled"
                }
            }

        except HttpError as error:
            print(f"Error al cancelar la cita: {error}")
            return {
                "message": "Ocurrió un error al cancelar la cita.",
                "status": "error",
                "error": str(error)
            }

        except Exception as e:
            print(f"Error inesperado: {str(e)}")
            return {
                "message": "Error inesperado al procesar la operación.",
                "status": "error",
                "error": str(e)
            }

        #---------------------------------------------------AIRTABLE----------------------------------------------------------------------
        
class AirtableAppointmentManager:
    def __init__(self, base_id, table_name, access_token):
        """
        Inicializa el cliente de Airtable con un token de acceso personal.

        Args:
            base_id (str): ID de la base de Airtable.
            table_name (str): Nombre de la tabla dentro de la base.
            access_token (str): Token de acceso personal para autenticar las solicitudes.
        """
        self.base_url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
        self.base_id = base_id
        self.access_token = access_token
        self.table_name = table_name
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }


    def create_record(self, fields, customer):
        """
        Crea un nuevo registro en una tabla, validando los datos antes de enviarlos.

        Args:
            fields (dict): Campos y valores para el nuevo registro.
            customer (dict): Datos del cliente asociados, incluyendo 'id_cliente'.

        Returns:
            dict: Respuesta de la API de Airtable o mensaje de error.
        """
        try:
            id_cliente = customer.get("id_cliente")
            if not id_cliente:
                return {
                    "message": "No se proporcionó un ID de cliente válido.",
                    "status": "error"
                }

            # Validar y convertir la fecha/hora de la cita
            fecha_original = fields.get("Fecha y hora de la cita")
            start_time = self.ajustar_fecha_año_actual(fecha_original)

            if not fecha_original:
                return {
                    "message": "No se proporcionó la fecha y hora de la cita.",
                    "status": "error"
                }

            if isinstance(start_time, str):
                try:
                    start_time = datetime.fromisoformat(start_time)
                except ValueError:
                    return {
                        "message": "El formato de fecha/hora de la cita no es válido. Use el formato ISO 8601.",
                        "status": "error"
                    }

            if start_time.tzinfo is None:
                
                start_time = start_time.replace(tzinfo=timezone(timedelta(hours=+6)))

            formatted_start_time = start_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

            # Validar que la cita tenga al menos 4 horas de anticipación
            current_time = datetime.now(timezone(timedelta(hours=-6)))   # Ajustar por zona horaria
            if start_time - current_time < timedelta(hours=4):
                return {
                    "message": "Para agendar una cita, se debe contar con al menos 4 horas de anticipación.",
                    "status": "error"
                }

            # Validar que la cita esté dentro del horario laboral (9 am - 7 pm)
            if not (9 <= start_time.hour < 19):
                return {
                    "message": "La cita debe ser agendada dentro del horario laboral: 9 am a 7 pm.",
                    "status": "error"
                }

            # Validar disponibilidad del horario
            filter_formula = f"{{Fecha y hora de la cita}} = '{formatted_start_time}'"
            url_check_time = f"{self.base_url}?filterByFormula={filter_formula}"
            time_response = requests.get(url_check_time, headers=self.headers)

            if time_response.status_code != 200:
                return {
                    "message": "No se pudo verificar la disponibilidad del horario. Por favor intente más tarde.",
                    "status": "error"
                }

            # Comprobar si el horario está ocupado
            occupied_records = time_response.json().get("records", [])
            if occupied_records:
                return {
                    "message": "El horario seleccionado ya está ocupado. Por favor seleccione otro horario.",
                    "status": "error"
                }

            airtable_fields = {
                "Asunto de la cita": fields.get("Asunto de la cita"),
                "Descripción de la cita": fields.get("Descripción de la cita"),
                "Fecha y hora de la cita": formatted_start_time,
                "ID del Cliente": [customer["id_cliente"]]  # Relación con tabla de clientes
            }
            data = {"fields": airtable_fields}

            response = requests.post(self.base_url, headers=self.headers, json=data)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Error al crear el registro: {e}")
            return {
                "message": "Ocurrió un error al intentar crear la cita. Por favor inténtelo más tarde.",
                "status": "error"
            }
        
    def ajustar_fecha_año_actual(self, fecha_str):
        """
        Ajusta el año de una fecha proporcionada a la fecha actual si el año es 2023.
        La fecha puede ser en formato "YYYY-MM-DD" o "YYYY-MM-DDTHH:MM:SS".
        
        Args:
            fecha_str (str): Fecha proporcionada como cadena.
            
        Returns:
            str: Fecha ajustada con el año actual en formato ISO 8601.
        """
        try:
            # Intentar convertir la fecha incluyendo la hora
            fecha = datetime.fromisoformat(fecha_str)
        except ValueError:
            try:
                # Intentar convertir solo la fecha (sin hora)
                fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Formato de fecha inválido: {fecha_str}")
        
        # Obtener el año actual
        ahora = datetime.now()
        
        # Ajustar el año si es 2023
        if fecha.year == 2023:
            fecha = fecha.replace(year=ahora.year)
        
        # Devolver la fecha ajustada, respetando si tenía hora o no
        if "T" in fecha_str:
            return fecha.isoformat()  # Formato ISO con hora
        else:
            return fecha.date().isoformat()  # Solo la fecha (YYYY-MM-DD)
        
    def reschedule_appointment(self, datos_reagendar, nueva_fecha):
        fecha_formateada = self.ajustar_fecha_año_actual(nueva_fecha)
        fecha_original = datos_reagendar.get("Fecha y hora de la cita")
        inicio_formateado = self.ajustar_fecha_año_actual(nueva_fecha)

        def to_iso_utc(date_time):
            if isinstance(date_time, str):
                date_time = datetime.fromisoformat(date_time)
            if date_time.tzinfo is None:
                date_time = date_time.replace(tzinfo=timezone.utc)
            return date_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        
        fecha_hora_cita = datos_reagendar.get("Fecha y hora de la cita") 
        fecha_hora_cita = to_iso_utc(inicio_formateado)
        fecha_formateada = to_iso_utc(fecha_formateada)

        current_time = datetime.now(timezone.utc)
        current_time = current_time - timedelta(hours=6)
        new_start_datetime = datetime.fromisoformat(fecha_formateada.replace("Z", "+00:00"))
        if new_start_datetime - current_time < timedelta(hours=4):
            return{
                "message": "Para agendar una cita deben haber al menos 4 horas de anticipación"
            }

        # Validar que la nueva fecha/hora esté dentro del horario laboral
        adjusted_time = new_start_datetime  # Ajustar a zona horaria local
        if not (9 <= adjusted_time.hour < 19):
            return{
                "message": "La cita debe ser agendada dentro del horario laboral. 9am a 7 pm"
            }

        phone = datos_reagendar.get("phone")
        full_name = datos_reagendar.get("full_name")
        filter_formula = f"AND({{Asunto de la cita}} = '{phone} - {full_name}', {{Fecha y hora de la cita}} = '{fecha_hora_cita}')"
        url_search = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}?filterByFormula={filter_formula}"
        search_response = requests.get(url_search, headers=self.headers)

        if search_response.status_code != 200:
            print("Código de estado:", search_response.status_code)
            print("Respuesta:", search_response.text)
            return {
                "message": "Ocurrió un error al consultar las citas. Por favor intentelo más tarde"
            }
    
        records = search_response.json().get("records", [])

        if not records:
            return {
                "message": "No se encontró la cita que está buscando. Proporcione los datos nuevamente"
            }

        record_id = records[0]["id"]
        current_description = records[0]["fields"].get("Descripción de la cita", "Sin descripción")
        current_subject = records[0]["fields"].get("Asunto de la cita", "Sin asunto")
        current_client_id = records[0]["fields"].get("ID del Cliente")
        print(current_client_id)

        filter_new_time = f"{{Fecha y hora de la cita}} = '{fecha_formateada}'"
        url_check_time = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}?filterByFormula={filter_new_time}"

        time_response = requests.get(url_check_time, headers=self.headers)

        if time_response.status_code != 200:
            print("Código de estado:", time_response.status_code)
            print("Respuesta:", time_response.text)
            return {
                "message": "Ocurrió un error al consultar la disponibilidad. Por favor, intentelo más tarde"
            }

        new_time_records = time_response.json().get("records", [])

        if new_time_records:
            return {
                "message": "El horario seleccionado ya está ocupado. Por favor seleccione otro horario."
            }

        new_description = f"{current_description} Reagendado a {fecha_formateada}"
        update_payload = {
            "fields": {
                "Estado": "Inactivo",
                "Descripción de la cita": new_description,
            }
        }

        update_url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}/{record_id}"
        update_response = requests.patch(update_url, headers=self.headers, data=json.dumps(update_payload))

        if update_response.status_code not in (200, 201):
            print("Código de estado:", update_response.status_code)
            print("Respuesta:", update_response.text)
            return {
                "message": "Ocurrió un error al actualizar el registro. Por favor intentelo más tarde"
            }

        print("Registro actualizado exitosamente.")


        new_record_payload = {
            "fields": {
                "Fecha y hora de la cita": fecha_formateada,
                "Asunto de la cita": current_subject,
                "ID del Cliente": current_client_id,
                "Descripción de la cita": f"{current_description} Reagendado"
            }
        }

        # Validar que la nueva fecha/hora esté dentro del horario laboral para el nuevo registro
        adjusted_new_time = new_start_datetime  # Ajustar a zona horaria local
        if not (9 <= adjusted_new_time.hour < 19):
            return{
                "message": "La cita debe ser agendada dentro del horario laboral. 9am a 7 pm"
            }

        print(new_record_payload)
        create_url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}"
        create_response = requests.post(create_url, headers=self.headers, data=json.dumps(new_record_payload))

        if create_response.status_code in (200, 201):
            print("Nuevo registro creado exitosamente.")
            return {
                "message": "Cita reagendada exitosamente y nuevo registro creado.",
                "data": {
                    "new_start_time": fecha_formateada,
                    "description": new_description
                }
            }
        else:
            print("Código de estado:", create_response.status_code)
            print("Respuesta:", create_response.text)
            return {
                "message": "Error al registrar el nuevo horario. Por favor, intentelo más tarde."
            }

        
    def cancel_appointment(self, fields):
        # Extraer valores requeridos de datos_cita
        phone = fields.get("phone")
        full_name = fields.get("full_name")
        start_time = fields.get("Fecha y hora de la cita")  # Formato "YYYY-MM-DDTHH:MM:SS"

        # Convertir la fecha/hora de la cita al formato adecuado para Airtable
        dt = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S")
        formatted_start_time = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        print("Formatted start_time:", formatted_start_time)

        # Crear la fórmula para filtrar el registro en Airtable
        filter_formula = (
            f"AND("
            f"{{Asunto de la cita}} = '{phone} - {full_name}', "
            f"{{Fecha y hora de la cita}} = '{formatted_start_time}'"
            f")"
        )
        print("Filtro para búsqueda:", filter_formula)

        # Buscar el registro en Airtable
        url_search = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}?filterByFormula={filter_formula}"
        search_response = requests.get(url_search, headers=self.headers)

        if search_response.status_code != 200:
            print("Código de estado:", search_response.status_code)
            print("Respuesta:", search_response.text)
            return {
                "message": "Error al buscar el registro. Por favor, inténtelo más tarde."
            }

        records = search_response.json().get("records", [])
        if not records:
            return {
                "message": "No se encontró el registro. Por favor verifique los datos e intente nuevamente."
            }

        # Tomar el primer registro coincidente
        record_id = records[0]["id"]

        # Actualizar el estado del registro a "Inactivo" (o "Cancelada", según tu lógica)
        update_payload = {
            "fields": {
                "Estado": "Inactivo"
            }
        }

        url_update = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}/{record_id}"
        update_response = requests.patch(url_update, headers=self.headers, data=json.dumps(update_payload))

        if update_response.status_code in [200, 204]:
            print("Registro actualizado exitosamente a Inactivo en Airtable.")
            return {
                "status": "success",
                "message": "La cita se ha cancelado exitosamente."
            }
        else:
            print("Código de estado:", update_response.status_code)
            print("Respuesta:", update_response.text)
            return {
                "message": "Error al cancelar la cita. Por favor, inténtelo más tarde."
            }
    
    def get_appointments(self, field, customer):
        """
        Consulta todas las citas de la tabla de Airtable.

        Returns:
            list: Una lista de registros (citas) obtenidos de Airtable.
        """
        id_cliente = customer["id_cliente_ai"]
        print(id_cliente)

        if not customer:
            raise ValueError("El filtro 'customer' es obligatorio.")

        try:
            records = []
            offset = None

            # Construir fórmula según el formato correcto
            if field:
                dt = datetime.strptime(field, "%Y-%m-%dT%H:%M:%S")
                formatted_start_time = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                print(formatted_start_time)
                filter_formula = f"AND({{ID del Cliente}}='{id_cliente}', {{Fecha y hora de la cita}}='{formatted_start_time}')"
            else:
                filter_formula = f"{{ID del Cliente}}='{id_cliente}'"

            encoded_formula = urllib.parse.quote(filter_formula)

            while True:
                url = f"{self.base_url}?filterByFormula={encoded_formula}"
                if offset:
                    url += f"&offset={offset}"

                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()

                records.extend(data.get("records", []))

                offset = data.get("offset")
                if not offset:
                    break
            
            print(records)
            return records

        except requests.exceptions.RequestException as e:
            print(f"Error al obtener citas: {e}")
            return{
                "message": "Error al obtener los horarios. Por favor, intentelo más tarde."
            }
        
    def check_availability(self, date, time=None):
        print("Hola")
        """
        Consulta la disponibilidad en Airtable.
        :param day: Fecha en formato YYYY-MM-DD (obligatorio).
        :param time: Hora específica en formato HH:MM (opcional).
        :return: Diccionario con la disponibilidad y respuesta legible.
        """
        try:
            # Validar el formato del día
            try:
                day_datetime = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                return {"success": "error", "message": "El formato del día debe ser YYYY-MM-DD."}

            # Construir la fórmula para filtrar por día
            fecha_formateada = self.ajustar_fecha_año_actual(date)

            day_filter = f"DATESTR({{Fecha y hora de la cita}}) = '{fecha_formateada}'"

            # Si se proporciona una hora, construir un filtro adicional
            if time:
                try:
                    time_datetime = datetime.strptime(f"{fecha_formateada}T{time}:00", "%Y-%m-%dT%H:%M:%S")
                    iso_time = time_datetime.isoformat()
                    formatted_start_time = time_datetime.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                    print(formatted_start_time)

                except ValueError:
                    return {"success": "error", "message": "El formato de la hora debe ser HH:MM."}

                time_filter = f"{{Fecha y hora de la cita}} = '{formatted_start_time}'"
                filter_formula = f"AND({day_filter}, {time_filter})"
            else:
                filter_formula = day_filter
            
            print(filter_formula)

            # Construir la URL para consultar Airtable
            url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}?filterByFormula={filter_formula}"

            # Realizar la consulta
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                return {
                    "success": "error",
                    "message": "Error al consultar la disponibilidad. Por favor, inténtelo más tarde."
                }
            

            records = response.json().get("records", [])
            print(records)

            # Procesar resultados
            if time:
                if records:
                    print("Ocupado")
                    return {
                        "success": "success",
                        "message": f"La hora {time} del día {date} ya está ocupada.",
                        "data": records
                    }
                else:
                    print("Libre")
                    return {
                        "success": "success",
                        "message": f"La hora {time} del día {date} está libre.",
                        "data": []
                    }
            else:
                if records:
                    occupied_times = [datetime.fromisoformat(record['fields']['Fecha y hora de la cita']).strftime("%H:%M") for record in records]
                    print("Ocupado")
                    return {
                        "success": "false",
                        "message": f"El día {date} no está disponible en los siguientes horarios: {', '.join(occupied_times)}.",
                        "data": records
                    }
                else:
                    print("Libre")
                    return {
                        "success": "success",
                        "message": f"El día {date} está completamente libre.",
                        "data": []
                    }

        except Exception as e:
            return {"success": "error", "message": f"Error inesperado: {str(e)}"}


