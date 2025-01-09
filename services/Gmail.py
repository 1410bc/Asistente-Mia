from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import base64
from email.mime.text import MIMEText

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',  # Para leer mensajes
          'https://www.googleapis.com/auth/gmail.send']      # Para enviar correos


class GmailManager:
    def __init__(self):
        self.service = self._authenticate()

    def _authenticate(self):
        creds = None

        # Cargar credenciales desde archivo
        if os.path.exists('token_gmail.json'):
            creds = Credentials.from_authorized_user_file('token_gmail.json', SCOPES)

        # Renovar credenciales si es necesario
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials_gmail.json', SCOPES)
                creds = flow.run_local_server(port=0)

            # Guardar las credenciales para uso futuro
            with open('token_gmail.json', 'w') as token:
                token.write(creds.to_json())

        return build('gmail', 'v1', credentials=creds)

    def list_messages(self, query='', max_results=10):
        '''
        Lista los mensajes en la cuenta de Gmail según la consulta proporcionada.

        :param query: Consulta de búsqueda (por ejemplo, "is:unread" para mensajes no leídos).
        :param max_results: Número máximo de resultados.
        :return: Lista de mensajes encontrados.
        '''
        try:
            results = self.service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
            messages = results.get('messages', [])
            if not messages:
                print("No se encontraron mensajes.")
            else:
                for message in messages:
                    msg = self.service.users().messages().get(userId='me', id=message['id']).execute()
                    print(f"Mensaje encontrado: {msg['snippet']} con el id: {message['id']}")
            return messages
        except HttpError as error:
            print(f"Ocurrió un error: {error}")
            return []

    def get_message(self, message_id):
        """
        Obtiene el contenido completo de un mensaje.

        :param message_id: ID del mensaje.
        :return: Contenido del mensaje.
        """
        try:
            message = self.service.users().messages().get(userId='me', id=message_id, format='full').execute()
            payload = message.get('payload', {})
            headers = payload.get('headers', [])
            subject = next((header['value'] for header in headers if header['name'] == 'Subject'), 'Sin asunto')
            body = base64.urlsafe_b64decode(payload.get('body', {}).get('data', '')).decode('utf-8', errors='ignore')

            print(f"Asunto: {subject}")
            print(f"Cuerpo: {body}")
            return message
        except HttpError as error:
            print(f"Ocurrió un error: {error}")
            return None

    def send_message(self, to, subject, body_text):
        """
        Envía un correo electrónico.

        :param to: Dirección de correo del destinatario.
        :param subject: Asunto del correo.
        :param body_text: Cuerpo del correo.
        :return: Respuesta del servicio Gmail.
        """
        try:
            message = MIMEText(body_text)
            message['to'] = to
            message['subject'] = subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            sent_message = self.service.users().messages().send(
                userId='me', body={'raw': raw_message}
            ).execute()
            print(f"Correo enviado exitosamente: {sent_message['id']}")
            return sent_message
        except HttpError as error:
            print(f"Ocurrió un error al enviar el correo: {error}")
            return None


#gmail = GmailManager()
#gmail.list_messages("is:unread", 1)
#gmail.get_message("1939d8ab247bb8e3")
#gmail.send_message("jslb_cafcb10@hotmail.com", "Mensaje enviado desde python via API", "BIENVENIDO A MI TEXTO DE PRUEBA")