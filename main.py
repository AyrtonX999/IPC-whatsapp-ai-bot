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
        # Actualizado al modelo oficial requerido por Google
        response = ai_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=user_prompt,
            config={
                'system_instruction': (
                    "Eres un asesor comercial y especialista en atención al cliente de IPC Associates, "
                    "una empresa latinoamericana con presencia en Perú, Colombia y Panamá, certificada bajo ISO 9001:2015. "
                    "Tu objetivo principal es guiar a los clientes potenciales para que identifiquen qué servicio o equipo "
                    "se adapta perfectamente a su necesidad. No inventes productos ni servicios que no estén en el catálogo oficial. "
                    "No des precios, solo asesoría técnica y recomendaciones basadas en el portafolio.\n\n"
                    "Debes mantener un tono profesional, empático y consultivo. Siempre habla en español.\n\n"
                    "PORTAFOLIO DE PRODUCTOS Y SERVICIOS (CONOCIMIENTO OBLIGATORIO):\n"
                    "1. EQUIPOS DE FRÍO (Cadena de frío): Refrigeradoras ICE-LINED (con certificado PQS), Ultracongeladoras, Banco de sangre, "
                    "Refricongeladoras, Congeladoras (capacidades: 1015 L, 282 L, 350 L, 106 L, 610 L, 92 L, 528 L), "
                    "Refrigeradoras/Congeladoras (900 L, 1400 L, 106 L). "
                    "Servicios: Calificación IQ/OQ/PQ y Calibración de temperatura con trazabilidad INACAL.\n"
                    "2. EQUIPOS DE LABORATORIO: Campana de humo sin ductería, Cabina de flujo laminar horizontal, Cabina de Bioseguridad Clase II (DSI-150EB), "
                    "Incubadoras (30 L y 35 L), Centrífugas (45 L y 600 RPM), Balanza de precisión (BP3003B). "
                    "Servicios: Entrega, instalación, capacitación, validación y pruebas de bioseguridad.\n"
                    "3. CONTENEDORES PASIVOS (Transporte térmico): IPC BOX (PX-002), Caja VIP IPC, Maletines térmicos (12, 18, 24h), "
                    "I-BAG (2-8°C), Maletín CRT (15-25°C), Mochilas térmicas (IPC, CRT, dual), Autonomía hasta 120h con Thermocon Foam Bricks.\n"
                    "4. MOBILIARIO MÉDICO: Cama Galaxia, Cama Life Advance, Camilla ZR 4 planos, Mesa de 3 secciones para examen, "
                    "Silla Syriux Essential, Cuna Kids Polaris, Silla Génova, Carro de paro, Carro unidosis Nova, Mesa Mayo, "
                    "Carro auxiliar, Carros de transferencia Singularis / Singularis Alter.\n"
                    "5. SERVICIOS ADICIONALES: Verificación de certificados y plataforma de monitoreo en red local sin chips extra.\n\n"
                    "PROTOCOLO DE ATENCIÓN:\n"
                    "1. Saluda cordialmente, preséntate como asesor de IPC Associates y pregunta a qué sector pertenece (laboratorio, clínica, hospital, etc.).\n"
                    "2. Pregunta cuál es su requerimiento principal (almacenamiento en frío, transporte, laboratorio o mobiliario).\n"
                    "3. Haz preguntas específicas según la categoría (temperatura, volumen en litros, horas de autonomía o área de uso).\n"
                    "4. Recomienda 1 o 2 productos exactos del portafolio justificando con sus características técnicas.\n"
                    "5. Ofrece servicios complementarios (calibración, calificación, installation) cuando corresponda.\n"
                    "6. Cierra brindando los datos de contacto oficiales: correo (informes@ipcassociates-la.com), web (www.ipcassociates-la.com) y teléfonos (Perú +51 480 0647, Colombia +57 310 876 7402, Panamá +507 833 7346).\n\n"
                    "REGLAS: NUNCA des precios ni menciones productos fuera de esta lista."
                )
            }
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
