import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os

SCOPES = ['https://www.googleapis.com/auth/documents']  # Acceso para trabajar con Google Docs


class GoogleDocsManager:
    def __init__(self):
        self.service = self._authenticate()

    def _authenticate(self):
        creds = None

        # Cargar credenciales desde archivo
        if os.path.exists('token_docs.json'):
            creds = Credentials.from_authorized_user_file('token_docs.json', SCOPES)

        # Renovar credenciales si es necesario
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                
                credentials_json = os.getenv('GOOGLE_DOCS_CREDENTIALS')
                if not credentials_json:
                    raise EnvironmentError("La variable de entorno 'GOOGLE_DOCS_CREDENTIALS' no está configurada.")
                
                credentials_dict = json.loads(credentials_json)

                # Crear el flujo de autenticación
                flow = InstalledAppFlow.from_client_config(credentials_dict, SCOPES)
                creds = flow.run_local_server(port=8080)

            # Guardar las credenciales para uso futuro
            with open('token_docs.json', 'w') as token:
                token.write(creds.to_json())

        return build('docs', 'v1', credentials=creds)

    def get_document(self, document_id):
        """
        Obtiene el contenido de un documento de Google Docs por su ID.

        :param document_id: ID del documento de Google Docs.
        :return: Contenido del documento.
        """
        try:
            document = self.service.documents().get(documentId=document_id).execute()
            title = document.get('title')
            body = document.get('body', {}).get('content', [])

            print(f"Título del documento: {title}")
            print("Contenido del documento:")

            text = ""
            for element in body:
                paragraph = element.get('paragraph')
                if paragraph:
                    for text_run in paragraph.get('elements', []):
                        text += text_run.get('textRun', {}).get('content', '')

            print(text)
            return document
        except HttpError as error:
            print(f"Ocurrió un error al obtener el documento: {error}")
            return None

    def create_document(self, title, content):
        """
        Crea un nuevo documento de Google Docs con el título y contenido proporcionados.

        :param title: Título del documento.
        :param content: Contenido del documento.
        :return: ID del documento creado.
        """
        try:
            document = self.service.documents().create(body={'title': title}).execute()
            document_id = document.get('documentId')

            # Agregar contenido al documento
            requests = [
                {
                    'insertText': {
                        'location': {'index': 1},
                        'text': content
                    }
                }
            ]
            self.service.documents().batchUpdate(
                documentId=document_id, body={'requests': requests}
            ).execute()

            print(f"Documento creado con éxito. ID: {document_id}")
            return document_id
        except HttpError as error:
            print(f"Ocurrió un error al crear el documento: {error}")
            return None
