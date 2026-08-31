from fastapi import FastAPI, Request, Response
from google import genai
import requests
import os

app = FastAPI()

# Credenciales de Meta
ACCESS_TOKEN = "EAAP4ZAc70DrQBSbsPK5QpbbBtVAhILGBEU0qC4JFrxB04xqtPBizQomzM3SFbsEmmyDIrIsW9t2YhM2EfxzzIXdj6ZATZBFZBqQ7qYyh66RkWMOBptksafNnIx6OmSs5UDkjjwJQsDD1mw9uRkMiNghvNPHLn5QKAfGVy1Kqq8LGsp8ZAY3iqB5jQ6F1VDgZDZD"
PHONE_NUMBER_ID = "1350712648117758"
VERIFY_TOKEN = "IPC_SECRET_TOKEN_2026"

# Inicializar cliente de Gemini de forma segura usando variables de entorno
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ai_client = genai.Client(api_key=GEMINI_API_KEY)

@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    return Response(content="Token inválido", status_code=403)

@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        data = await request.json()
        
        entry = data.get('entry', [])[0]
        changes = entry.get('changes', [])[0]
        value = changes.get('value', {})
        
        if 'messages' in value:
            message_obj = value['messages'][0]
            number = message_obj.get('from')
            
            if message_obj.get('type') == 'text':
                text_received = message_obj['text']['body']
                
                print(f"Mensaje recibido de {number}: {text_received}")
                
                ai_response = ask_gemini(text_received)
                send_whatsapp_message(number, ai_response)
                
    except Exception as e:
        print("Error al procesar webhook:", e)
        
    return {"status": "ok"}

def ask_gemini(user_prompt: str) -> str:
    try:
        # Corregido al modelo oficial disponible
        response = ai_client.models.generate_content(
            model='gemini-1.5-flash',
            contents=user_prompt,
        )
        return response.text
    except Exception as e:
        print("Error detallado en Gemini:", e)
        return "Lo siento, tuve un problema al procesar tu consulta con la IA."

def send_whatsapp_message(to_number: str, message_text: str):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message_text}
    }
    res = requests.post(url, json=payload, headers=headers)
    print("Respuesta Meta API:", res.status_code)
