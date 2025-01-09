import requests
from datetime import datetime, timedelta, timezone
import json

import sys

class AuthenticationError(Exception):
    pass

class WhatsApp_Manager:
    def __init__(self, access_token, phone_number_id, api_version="v21.0"):
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"

    def send_message(self, phone_number, message):
        """
        Envía un mensaje a través de la Cloud API de WhatsApp.

        :param phone_number: Número de WhatsApp del destinatario.
        :param message: Texto del mensaje a enviar.
        :return: Respuesta de la API de WhatsApp.
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": message}
        }

        response = requests.post(self.base_url, headers=headers, data=json.dumps(payload))
        return response
    