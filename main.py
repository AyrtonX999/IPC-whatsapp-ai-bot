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

# URL de Power Automate configurada
POWER_AUTOMATE_URL = "https://fb058902f544ecd1b22017ca5493c8.e6.environment.api.powerplatform.com:443/powerautomate/automations/direct/cu/23/workflows/78404d5c51db480ca90b73a09d065ffe/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=KyzmlX8s2l8BwZaGuWTiq-B_J2tXWFRsdRXJeY1i9K0"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ai_client = genai.Client(api_key=GEMINI_API_KEY)

active_chats = {}
last_message_times = {}
last_processed_timestamps = {}  # Control anti-ráfagas de Meta
last_lead_notifications = {}    # Control anti-spam para Power Automate
INACTIVITY_TIMEOUT = 3600
LEAD_COOLDOWN = 1800            # 30 minutos de espera antes de mandar otro correo al mismo cliente

SYSTEM_INSTRUCTION_TEXT = (
    "REGLA CRÍTICA DE SALUDO:\n"
    "- Utiliza el saludo exacto '¡Hola! Bienvenido al chat de IPC Associates. Soy tu asesor técnico y comercial IPC DOC.' **ÚNICAMENTE en el primer mensaje de toda la conversación**.\n"
    "- **PROHIBIDO** volver a saludar, repetir la bienvenida o decir 'hola de nuevo' en los mensajes posteriores de la misma charla.\n\n"
    "PORTAFOLIO OFICIAL:\n"
    "1. EQUIPOS DE FRÍO: Refrigeradoras ICE-LINED (certificado PQS), Ultracongeladoras, Banco de sangre, Refricongeladoras, Congeladoras. Servicios: Calificación IQ/OQ/PQ y Calibración de temperatura con trazabilidad INACAL.\n"
    "2. EQUIPOS DE LABORATORIO Y MONITOREO: Campanas de humo sin ductería, Cabinas de flujo laminar, Cabinas de Bioseguridad Clase II (DSI-150EB), Incubadoras (30L y 35L), Centrífugas y Balanza de precisión (BP3003B).\n"
    "   - **MONITOREO ELITECH:** Los equipos Elitech (como el RCW 360 WiFi, termohigrómetros y registradores) son **dispositivos electrónicos de medición y monitoreo**, NUNCA cajas ni contenedores térmicos pasivos.\n"
    "3. CONTENEDORES PASIVOS: IPC BOX (PX-002), Caja VIP IPC, Maletines térmicos, I-BAG, Maletín CRT, Mochilas térmicas y Thermocon Foam Bricks.\n"
    "4. MOBILIARIO MÉDICO: Cama Galaxia, Cama Life Advance, Camilla ZR, Mesa de examen, Silla Syriux, Cuna Kids Polaris, Silla Génova, Carro de paro, Carro unidosis, Mesa Mayo y carros de transferencia.\n"
    "5. SERVICIOS ADICIONALES: Verificación de certificados de calibración y Monitoreo local.\n\n"
    "REGLAS ESTRICTAS DE RESPUESTA Y DERIVACIÓN:\n"
    "1. **DUDA O AMBIGÜEDAD:** Si el cliente menciona un código, modelo o producto y **no estás 100% seguro** de a qué categoría pertenece, **NUNCA inventes su descripción**. En su lugar, haz una pregunta de aclaración amigable (por ejemplo: '¿Quizás te refieres al registrador de monitoreo Elitech RCW 360 o a otro modelo específico?').\n"
    "2. **GUÍA Y OFERTA:** Orienta al cliente de forma precisa sobre el producto real una vez identificado.\n"
    "3. **PRODUCTOS FUERA DE PORTAFOLIO:** Si el producto definitivamente no se encuentra en el portafolio, dile amablemente que un asesor comercial lo atenderá a medida y activa la derivación.\n"
    "4. **CUÁNDO DERIVAR (Activar [DERIVAR_VENTAS]):** Solo incluye el texto `[DERIVAR_VENTAS]` al final del mensaje si el cliente pide cotización formal, precios, stock o hablar con un asesor humano.\n"
    "5. No escribas nada en negrita ni pongas asterisco.\n"
    "6. Si te preguntan donde ver Certificado de Calibracion indicas que pueden verlo en https://ipcassociates-la.com/certificados/.\n"
    "7. **FICHAS TÉCNICAS:** Si solicitan fichas técnicas, facilítale el enlace: https://ipcassociates-la.com/fichas.html\n"
    "8. Muestra los servicios de forma breve y ofrece al cliente utilizar la herramienta de Interpolacion para calibraciones mediante este link https://ipcassociates-la.com/interpolacion.html\n"
    "9. Mantén las respuestas directas, concisas y sin textos demasiado largos."
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
            
            # Soporte para nombres de usuario (@) donde 'from' puede venir mapeado en contacts
            if not number and 'contacts' in value and len(value['contacts']) > 0:
                number = value['contacts'][0].get('wa_id')
            
            if number == PHONE_NUMBER_ID:
                return {"status": "ok"}
            
            if number and message_obj.get('type') == 'text':
                text_received = message_obj['text']['body']
                
                current_time = time.time()
                if number in last_processed_timestamps:
                    last_msg, last_time = last_processed_timestamps[number]
                    if last_msg == text_received and (current_time - last_time) < 5:
                        print(f"Mensaje duplicado bloqueado por ráfaga de {number}: {text_received}")
                        return {"status": "ok"}
                
                last_processed_timestamps[number] = (text_received, current_time)
                print(f"Mensaje recibido de {number}: {text_received}")
                
                ai_response = ask_gemini_comercial(number, text_received)
                
                if ai_response:
                    if "[DERIVAR_VENTAS]" in ai_response:
                        clean_response = ai_response.replace("[DERIVAR_VENTAS]", "").strip()
                        send_whatsapp_message(number, clean_response)
                        
                        should_send_email = True
                        if number in last_lead_notifications:
                            if (current_time - last_lead_notifications[number]) < LEAD_COOLDOWN:
                                should_send_email = False
                                print(f"Alerta a Power Automate omitida (cooldown activo) para el número {number}")

                        if should_send_email:
                            last_lead_notifications[number] = current_time
                            payload_lead = {
                                "telefono": number,
                                "mensaje": text_received,
                                "respuesta_bot": clean_response
                            }
                            try:
                                res_pa = requests.post(POWER_AUTOMATE_URL, json=payload_lead)
                                print("Alerta enviada a Power Automate. Estado:", res_pa.status_code)
                            except Exception as pa_err:
                                print("Error al notificar a Power Automate:", pa_err)
                    else:
                        send_whatsapp_message(number, ai_response)
                    
    except Exception as e:
        print("Error general en webhook:", e)
        
    return {"status": "ok"}

def ask_gemini_comercial(user_number: str, user_prompt: str) -> str:
    max_retries = 1
    for attempt in range(max_retries):
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
            print(f"Intento {attempt + 1} - Error detallado en Gemini: {e}")
            if user_number in active_chats:
                del active_chats[user_number]
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
    print(f"BOT RESPONDIÓ a {to_number}: {message_text} | Estado Meta: {res.status_code}")
