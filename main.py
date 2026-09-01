from fastapi import FastAPI, Request, Response
from google import genai
import requests
import os
import time

app = FastAPI()

# Credenciales de Meta
ACCESS_TOKEN = "EAAP4ZAc70DrQBSbsPK5QpbbBtVAhILGBEU0qC4JFrxB04xqtPBizQomzM3SFbsEmmyDIrIsW9t2YhM2EfxzzIXdj6ZATZBFZBqQ7qYyh66RkWMOBptksafNnIx6OmSs5UDkjjwJQsDD1mw9uRkMiNghvNPHLn5QKAfGVy1Kqq8LGsp8ZAY3iqB5jQ6F1VDgZDZD"
PHONE_NUMBER_ID = "1350712648117758"
VERIFY_TOKEN = "IPC_SECRET_TOKEN_2026"

AGENTE_COMERCIAL_NUMBER = "51924726495"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ai_client = genai.Client(api_key=GEMINI_API_KEY)

active_chats = {}
last_message_times = {}
INACTIVITY_TIMEOUT = 3600

SYSTEM_INSTRUCTION_TEXT = (
    "Eres un asesor técnico estricto de IPC Associates. "
    "REGLAS ABSOLUTAS:\n"
    "1. Cero saludos largos, cero presentaciones repetitivas. Ve directo al grano.\n"
    "2. Responde en máximo 1 o 2 párrafos muy breves y directos exclusivamente a lo que te preguntan.\n"
    "3. Portafolio válido: Equipos de frío (Ice-Lined, ultracongeladoras, bancos de sangre), "
    "Equipos de laboratorio (Campanas, bioseguridad, incubadoras), Contenedores pasivos y Mobiliario médico. Nunca inventes precios ni productos ajenos.\n"
    "4. Si el cliente muestra interés de compra o pide cotización, responde puntualmente y añade obligatoriamente al final la frase exacta: [DERIVAR_VENTAS]."
)

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

        if 'messages' in value and len(value['messages']) > 0:
            message_obj = value['messages'][0]
            number = message_obj.get('from')
            
            # Evitar estrictamente que el bot procese sus propios mensajes enviados (esto rompe el bucle)
            if number == PHONE_NUMBER_ID:
                return {"status": "ok"}
            
            if not number and 'contacts' in value and len(value['contacts']) > 0:
                number = value['contacts'][0].get('wa_id')
            
            if number and message_obj.get('type') == 'text':
                text_received = message_obj['text']['body']
                print(f"Mensaje recibido de {number}: {text_received}")
                
                ai_response = ask_gemini_comercial(number, text_received)
                
                # Si ai_response está vacío por un error, no enviamos nada por WhatsApp para evitar bucles
                if ai_response:
                    if "[DERIVAR_VENTAS]" in ai_response:
                        clean_response = ai_response.replace("[DERIVAR_VENTAS]", "").strip()
                        send_whatsapp_message(number, clean_response)
                        
                        alerta_texto = (
                            f"🚨 *LEAD DETECTADO*\n\n"
                            f"📱 *Cliente:* +{number}\n"
                            f"💬 *Interés:* {clean_response}"
                        )
                        send_whatsapp_message(AGENTE_COMERCIAL_NUMBER, alerta_texto)
                    else:
                        send_whatsapp_message(number, ai_response)
                    
    except Exception as e:
        print("Error general en webhook:", e)
        
    return {"status": "ok"}

def ask_gemini_comercial(user_number: str, user_prompt: str) -> str:
    try:
        current_time = time.time()
        
        if user_number in last_message_times:
            if current_time - last_message_times[user_number] > INACTIVITY_TIMEOUT:
                if user_number in active_chats:
                    del active_chats[user_number]
        
        last_message_times[user_number] = current_time

        if user_number not in active_chats:
            active_chats[user_number] = ai_client.chats.create(
                model='gemini-3.6-flash',
                config={
                    'system_instruction': SYSTEM_INSTRUCTION_TEXT
                }
            )
        
        chat_session = active_chats[user_number]
        response = chat_session.send_message(user_prompt)
        
        return response.text
    except Exception as e:
        print("Error detallado en Gemini:", e)
        # IMPORTANTE: Ya no devolvemos texto de error para evitar que el bot se responda a sí mismo
        return ""

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
    print("Respuesta Meta API para", to_number, ":", res.status_code)
