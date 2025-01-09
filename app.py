from flask import Flask, request, jsonify
import requests
#import functions
import openai
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build

from services.GoogleCalendar import GoogleCalendarManager, AirtableAppointmentManager
from services.AirTable import AirtablePATManager
from services.Gmail import GmailManager
from services.GoogleDocs import GoogleDocsManager
from services.WhatsApp import WhatsApp_Manager

app = Flask(__name__)


openai.api_key = os.getenv("OPENAI_API_KEY")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_BUSINESS_ID = '439452585928337'
BASE_URL = f"https://graph.facebook.com/v16.0/{WHATSAPP_BUSINESS_ID}/messages"


SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

#creds = functions.authenticate_google()

user_threads = {}

@app.route("/")
def home():
    return "Asistente Bellachik está en línea"

app = Flask(__name__)



@app.route('/send_whatsapp_message', methods=['POST'])
def send_whatsapp_message():
    """
    Endpoint para enviar un mensaje usando WhatsAppManager.
    Espera un JSON con la estructura:
    {
      "phone_number": "<whatsapp_phone_number>",  # Ejemplo: "5491112345678"
      "message": "Mensaje de prueba"
    }
    """
    whatsapp_manager = WhatsApp_Manager(WHATSAPP_ACCESS_TOKEN, PHONE_NUMBER_ID)

    body = request.get_json()
    if not body:
        return jsonify({"error": "Missing JSON body"}), 400

    phone_number = body.get('phone_number')
    message = body.get('message')

    if not phone_number or not message:
        return jsonify({"error": "Missing phone_number or message"}), 400

    # Usamos la clase WhatsAppManager para enviar el mensaje
    response = whatsapp_manager.send_message(phone_number, message)

    if response.status_code == 200:
        return jsonify({
            "status": "success",
            "data": response.json()
        }), 200
    else:
        return jsonify({
            "status": "error",
            "code": response.status_code,
            "data": response.json()
        }), response.status_code


@app.route('/asistente_bellachik', methods=['POST'])
def asistente_bellachik():   
    try:
        # Obtener datos de la solicitud
        data = request.get_json()
        if data is None or 'message' not in data or 'customer' not in data:
            return jsonify({'status': 'error', 'message': 'Se requieren los campos "message" y "customer" en el JSON.'}), 400

        user_message = data['message']
        customer = data['customer']  # Información del cliente enviada en el request
        thread_id = customer.get('hilo_conversacion')
        print(f"Mensaje del usuario ({thread_id}): {user_message}")
        
        #En caso de no tener thread_id, se crea un nuevo hilo
        if not thread_id:
            thread = openai.beta.threads.create()
            thread_id = thread.id
            print(f"Nuevo thread_id creado: {thread_id}")
        
        # Agregar el mensaje del usuario al hilo
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message,
        )

        # Ejecutar el asistente
        assistant_id = os.getenv("ASSISTANT_ID")
        run = openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
        )

        # Manejar estado del run
        while run.status not in ("completed", "failed", "requires_action"):
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id,
            )
            
        if run.status == "requires_action":
            
            tools_to_call = run.required_action.submit_tool_outputs.tool_calls
            tool_outputs_array = []  # Array para almacenar las respuestas de las herramientas
            
            # Instanciar el gestor de Google Calendar
            calendar_manager = GoogleCalendarManager()

             # Configuración de Airtable        
            base_id = os.getenv("BASE_ID")
            access_token = os.getenv("ACCESS_TOKEN")
            table_name = "Citas"

            # # Crear instancia del manejador de Airtable
            airtable_manager = AirtablePATManager(base_id, access_token)
            appointment_manager = AirtableAppointmentManager(base_id, table_name, access_token)

            # Diccionario de mapeo de funciones
            function_map = {
                #Funciones para citas AIRTBALE
                "crear_citas": lambda **kwargs: appointment_manager.create_record(
                    fields=kwargs.get("datos_cita"),
                    customer=customer
                ),
                    #"reschedule_appointment": appointment_manager.reschedule_appointment,
                "actualizar_citas": lambda datos_reagendar, nueva_fecha: appointment_manager.reschedule_appointment(
                    datos_reagendar,
                    nueva_fecha
                ),
                "cancelar_cita": lambda **kwargs: appointment_manager.cancel_appointment(
                    fields=kwargs.get("datos_cita")
                ),
                "get_appointments": lambda **kwargs: appointment_manager.get_appointments(
                    field=kwargs.get("Fecha y hora de la cita"),
                    customer=customer
                ),
                "check_availability": appointment_manager.check_availability,
                "list_google_calendars": calendar_manager.list_calendars,
                
                "consultar_datos_cliente": lambda: format_customer_information(customer),
                "actualizar_cliente": lambda **kwargs: airtable_manager.update_record(
                    table_name="Clientes",
                    record_id=customer.get("id_cliente"),  # Se toma del objeto `customer` en el backend
                    fields=kwargs.get("campos_actualizar")  # Directamente del parámetro recibido
                ),
                "suscripcion_cliente": lambda: airtable_manager.update_record(
                    table_name="Clientes",
                    record_id=customer.get("id_cliente"),
                    fields={"Suscrito": False}
                ),
                "interaccion_humana": lambda asunto, descripcion: handle_human_interaction(
                    asunto=asunto,
                    descripcion=descripcion,
                    customer=customer,
                    airtable_manager=airtable_manager
                )
            }
            
            for tool_call in tools_to_call:
                print(tool_call)
                tool_name = tool_call.function.name
                tool_arguments = json.loads(tool_call.function.arguments)  # Parsear argumentos de la herramienta
                
                print(f"Procesando herramienta: {tool_name}")
                print(f"Argumentos: {tool_arguments}")
                
                if tool_name in function_map:
                    # Llamar a la función mapeada dinámicamente
                    function = function_map[tool_name]
                    try:
                        # Ejecutar la función con los argumentos descompuestos
                        result = function(**tool_arguments)
                        print(f"Resultado de {tool_name}: {result}")
                        
                        tool_outputs_array.append({
                            "tool_call_id": tool_call.id,
                            "output": json.dumps(result) 
                        })

                    except Exception as e:
                        print(f"Error al ejecutar {tool_name}: {str(e)}")
                        tool_outputs_array.append({
                            "tool_call_id": tool_call.id,
                            "output": json.dumps({"error": str(e)})
                        })
                
                else:
                    print(f"Herramienta desconocida: {tool_name}")
                    tool_outputs_array.append({
                        "tool_call_id": tool_call.id,
                        "output": json.dumps({"error": f"Tool {tool_name} not implemented"})
                    })
                    
            # Subir los resultados de las herramientas a OpenAI
            run = openai.beta.threads.runs.submit_tool_outputs(
                thread_id=thread_id,
                run_id=run.id,
                tool_outputs=tool_outputs_array
            )

            # Esperar nuevamente a que el asistente genere su respuesta final para tenerla disponible en el arreglo de respuesta
            while run.status not in ("completed", "failed"):
                run = openai.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id,
                )

        # **RECUPERAR LOS MENSAJES ACTUALIZADOS DEL HILO**
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        responses = [
            {"role": msg.role, "content": msg.content[0].text.value, "thread_id": thread_id}
            for msg in messages
        ]
        
        return jsonify({'status': 'success', 'messages': responses}), 200
        #return jsonify({'status': 'success', 'message': last_assistant_message, "thread_id": thread_id}), 200

    except Exception as e:
        print(f'Error inesperado: {str(e)}')
        return jsonify({'status': 'error', 'message': f'Error inesperado: {str(e)}'}), 500


def format_customer_information(customer_data):
    
    try:
        print("Llamando a la funcion")
        print(customer_data)

        # Preparar los datos disponibles del cliente
        formatted_info = []
        if customer_data.get("nombre_completo"):
            formatted_info.append(f"Nombre completo: {customer_data['nombre_completo']}")
        if customer_data.get("correo_electronico"):
            formatted_info.append(f"Correo electrónico: {customer_data['correo_electronico']}")
        if customer_data.get("telefono_movil"):
            formatted_info.append(f"Teléfono móvil: {customer_data['telefono_movil']}")
        if customer_data.get("domicilio"):
            formatted_info.append(f"Domicilio: {customer_data['domicilio']}")
        if customer_data.get("fecha_nacimiento"):
            formatted_info.append(f"Fecha de nacimiento: {customer_data['fecha_nacimiento']}")
        if customer_data.get("edad"):
            formatted_info.append(f"Edad: {customer_data['edad']} años")
        if customer_data.get("sexo"):
            formatted_info.append(f"Sexo: {customer_data['sexo']}")

        # Generar el mensaje formateado
        mensaje = "Estos son tus datos registrados:\n" + "\n".join(formatted_info)
        
        print(mensaje)

        return {
            "status": "success",
            "message": mensaje
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Ocurrió un error al formatear la información del cliente: {str(e)}"
        }
        
def handle_human_interaction(asunto, descripcion, customer, airtable_manager):
    try:
        # Actualizar el cliente en la tabla "Clientes"
        update_result = airtable_manager.actualizar_cliente(
            id_cliente=customer["id_cliente"],
            campos_actualizar={"Modo de Conversación": "Manual"}
        )
        print("Cliente actualizado:", update_result)
        
        data_request = {
            "fields": {
                "Tipo": "Alerta",
                "Asunto": asunto,
                "Descripción": descripcion,
                "Medio de Envío": "WhatsApp",
                "Id del Cliente": [customer["id_cliente"]],
            }
        }

        notification_result = airtable_manager.create_record("Notificaciones", data_request)
        
        if notification_result:
            print("Registro creado en Airtable:", notification_result)
        else:
            print("Error al crear el registro en Airtable")

        return {
            "status": "success",
            "message": "Interacción humana registrada y cliente actualizado.",
            "details": {
                "cliente_actualizado": update_result,
                "notificacion_creada": notification_result
            }
        }

    except Exception as e:
        print(f"Error al manejar interacción humana: {str(e)}")
        return {
            "status": "error",
            "message": f"Error al manejar interacción humana: {str(e)}"
        }


if __name__ == '__main__':
    #app.run(host='0.0.0.0', port=5000)
    app.run()