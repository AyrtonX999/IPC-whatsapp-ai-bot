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
    "Eres un asesor técnico y comercial de IPC Associates. \n"
    "PORTAFOLIO OFICIAL:\n"
    "1. EQUIPOS DE FRÍO: Refrigeradoras ICE-LINED (certificado PQS), Ultracongeladoras, Banco de sangre, Refricongeladoras, Congeladoras. Servicios: Calificación IQ/OQ/PQ y Calibración de temperatura con trazabilidad INACAL.\n"
    "2. EQUIPOS DE LABORATORIO: Campanas de humo sin ductería, Cabinas de flujo laminar, Cabinas de Bioseguridad Clase II (DSI-150EB), Incubadoras (30L y 35L), Centrífugas y Balanza de precisión (BP3003B).\n"
    "3. CONTENEDORES PASIVOS: IPC BOX (PX-002), Caja VIP IPC, Maletines térmicos, I-BAG, Maletín CRT, Mochilas térmicas y Thermocon Foam Bricks.\n"
    "4. MOBILIARIO MÉDICO: Cama Galaxia, Cama Life Advance, Camilla ZR, Mesa de examen, Silla Syriux, Cuna Kids Polaris, Silla Génova, Carro de paro, Carro unidosis, Mesa Mayo y carros de transferencia.\n"
    "5. SERVICIOS ADICIONALES: Verificación de certificados de calibración y Monitoreo local.\n\n"
    "REGLAS ESTRICTAS DE RESPUESTA:\n"
    "1. Ve directo al grano. Cero saludos largos o presentaciones repetitivas si ya se saludó.\n"
    "2. **DERIVACIÓN COMERCIAL:** Si el cliente pide un servicio o producto fuera de este portafolio (como calibración de pistolas IR, termómetros externos, etc.), muestra total disposición y activa la derivación. O bien, si muestra interés de compra o pide hablar con un asesor, responde textualmente al final de tu mensaje:\n"
    "[DERIVAR_VENTAS] Un asesor comercial se comunicará con usted a la brevedad."
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
            
            # Bloqueo total para evitar que el bot procese sus propios mensajes enviados
            if number == PHONE_NUMBER_ID:
                return {"status": "ok"}
            
            if not number and 'contacts' in value and len(value['contacts']) > 0:
                number = value['contacts'][0].get('wa_id')
            
            if number and message_obj.get('type') == 'text':
                text_received = message_obj['text']['body']
                print(f"Mensaje recibido de {number}: {text_received}")
                
                ai_response = ask_gemini_comercial(number, text_received)
                
                if ai_response:
                    if "[DERIVAR_VENTAS]" in ai_response:
                        clean_response = ai_response.replace("[DERIVAR_VENTAS]", "").strip()
                        send_whatsapp_message(number, clean_response)
                        
                        alerta_texto = (
                            f"🚨 *NUEVO LEAD / DERIVACIÓN COMERCIAL*\n\n"
                            f"📱 *Número del cliente:* +{number}\n"
                            f"💬 *Último mensaje del cliente:* {text_received}\n"
                            f"🤖 *Respuesta del bot:* {clean_response}"
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
