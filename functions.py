import os
import sys
import json
import pickle
import requests
from pprint import pprint
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from datetime import datetime, timedelta, timezone
from google.oauth2.service_account import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ['https://www.googleapis.com/auth/calendar']

#Autenticacion de googl
def authenticate_google():
    """
    Maneja la autenticación con Google y devuelve las credenciales.
    """
    creds = None
    # Verificar si ya existe un token guardado
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    # Si no hay credenciales o son inválidas
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Cargar credenciales desde la variable de entorno
            credentials_json = os.getenv('CALENDAR_CREDENTIALS')
            if not credentials_json:
                raise EnvironmentError("La variable de entorno 'CALENDAR_CREDENTIALS' no está configurada.")
            
            credentials_dict = json.loads(credentials_json)

            # Crear el flujo de autenticación
            flow = InstalledAppFlow.from_client_config(credentials_dict, SCOPES)
            creds = flow.run_local_server(port=8080)

        # Guardar el token para futuras ejecuciones
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds

def create_google_calendar_event(creds, event_title, start_time, end_time):

    service = build('calendar', 'v3', credentials=creds)

    event = {
        'summary': event_title,
        'start': {
            'dateTime': start_time,
            'timeZone': 'America/Mexico_City',
        },
        'end': {
            'dateTime': end_time,
            'timeZone': 'America/Mexico_City',
        },
    }

    event_result = service.events().insert(
        calendarId='c_5429309c7c93803f3c31f144ef187db179ada2d6ad3d527aba230d3293704913@group.calendar.google.com', 
        body=event
    ).execute()
    
    print(f"Evento creado: {event_result.get('htmlLink')}")
    return event_result

def get_google_calendar_events(creds, time_min, time_max):

    service = build('calendar', 'v3', credentials=creds)

    events_result = service.events().list(
        calendarId='c_5429309c7c93803f3c31f144ef187db179ada2d6ad3d527aba230d3293704913@group.calendar.google.com',  
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(f"Evento: {event['summary']}, Inicio: {start}")
    return events

from datetime import datetime, timedelta
import sys
from googleapiclient.discovery import build

def update_google_calendar_event_by_details(creds, event_title, start_time, updated_title=None, updated_start=None, updated_end=None):
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

        events = get_google_calendar_events(creds, time_min, time_max)

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


def delete_google_calendar_event_by_details(creds, event_title, start_time):
    service = build('calendar', 'v3', credentials=creds)

    try:
        start_datetime = datetime.fromisoformat(start_time)
        time_min = (start_datetime - timedelta(minutes=359)).isoformat() + "Z"
        time_max = (start_datetime + timedelta(minutes=361)).isoformat() + "Z"
        start_time_z = (start_datetime).isoformat() +"-06:00"

        events = get_google_calendar_events(creds,time_min, time_max)

        for event in events:
            if event['summary'] == event_title and event['start']['dateTime'] == start_time_z:
                service.events().delete(
                    calendarId='c_5429309c7c93803f3c31f144ef187db179ada2d6ad3d527aba230d3293704913@group.calendar.google.com',
                    eventId=event['id']
                ).execute()

                print(f"Evento eliminado: {event.get('summary')} - {event.get('start')['dateTime']}")
                return {"status": "success", "message": "Evento eliminado con éxito."}

        return {"status": "not_found", "message": f"No se encontró un evento con el título '{event_title}' y la hora de inicio '{start_time_z}'."}

    except Exception as e:
        print(f"Error al eliminar el evento: {str(e)}")
        return {"status": "error", "message": str(e)}

