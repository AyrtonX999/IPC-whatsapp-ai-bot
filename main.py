```python
from fastapi import FastAPI, Request, Response
from google import genai
import requests
import os
import json

app = FastAPI()

# ============================================================
# CREDENCIALES
# ============================================================

# IMPORTANTE:
# Guarda estos valores como variables de entorno.
ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("META_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "IPC_SECRET_TOKEN_2026")

# Número al que se notificará la derivación comercial
AGENTE_COMERCIAL_NUMBER = "51924726495"

# ============================================================
# GEMINI
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("ADVERTENCIA: GEMINI_API_KEY no está configurada.")

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# ============================================================
# MEMORIA DE CONVERSACIONES
# ============================================================

# La clave puede ser:
# - número telefónico
# - BSUID
#
# Esto permite que funcionen tanto usuarios normales como
# usuarios que utilizan username de WhatsApp.

active_chats = {}

# ============================================================
# INSTRUCCIONES DE GEMINI
# ============================================================

SYSTEM_INSTRUCTION_TEXT = (
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

    "2. EQUIPOS DE LABORATORIO: Campana de humo sin ductería, Cabina de flujo laminar horizontal, "
    "Cabina de Bioseguridad Clase II (DSI-150EB), Incubadoras (30 L y 35 L), "
    "Centrífugas (45 L y 600 RPM), Balanza de precisión (BP3003B). "
    "Servicios: Entrega, instalación, capacitación, validación y pruebas de bioseguridad.\n"

    "3. CONTENEDORES PASIVOS (Transporte térmico): IPC BOX (PX-002), Caja VIP IPC, "
    "Maletines térmicos (12, 18, 24h), I-BAG (2-8°C), Maletín CRT (15-25°C), "
    "Mochilas térmicas (IPC, CRT, dual), Autonomía hasta 120h con Thermocon Foam Bricks.\n"

    "4. MOBILIARIO MÉDICO: Cama Galaxia, Cama Life Advance, Camilla ZR 4 planos, "
    "Mesa de 3 secciones para examen, Silla Syriux Essential, Cuna Kids Polaris, "
    "Silla Génova, Carro de paro, Carro unidosis Nova, Mesa Mayo, "
    "Carro auxiliar, Carros de transferencia Singularis / Singularis Alter.\n"

    "5. SERVICIOS ADICIONALES: Verificación de certificados y plataforma de monitoreo "
    "en red local sin chips extra.\n\n"

    "PROTOCOLO DE ATENCIÓN:\n"

    "1. Saluda cordialmente, preséntate como asesor de IPC Associates y pregunta a qué sector pertenece "
    "(laboratorio, clínica, hospital, etc.).\n"

    "2. Pregunta cuál es su requerimiento principal "
    "(almacenamiento en frío, transporte, laboratorio o mobiliario).\n"

    "3. Haz preguntas específicas según la categoría "
    "(temperatura, volumen en litros, horas de autonomía o área de uso).\n"

    "4. Recomienda 1 o 2 productos exactos del portafolio justificando con sus características técnicas.\n"

    "5. CIERRE Y DERIVACIÓN: Después de entregar toda la información y la recomendación técnica, "
    "pregunta amablemente al cliente si se encuentra interesado para derivarlo con un Agente Comercial.\n"

    "6. DETECCIÓN DE INTERÉS: Si el cliente responde afirmativamente "
    "(por ejemplo: 'sí', 'estoy interesado', 'quiero que me contacten', 'me avisan'), "
    "DEBES incluir obligatoriamente en tu respuesta la frase exacta: "
    "[DERIVAR_VENTAS] seguida de un resumen breve del equipo o servicio que le interesa y sus datos.\n"

    "7. Cierra brindando los datos de contacto oficiales: "
    "correo (informes@ipcassociates-la.com), "
    "web (www.ipcassociates-la.com) y "
    "teléfonos (Perú +51 480 0647, Colombia +57 310 876 7402, Panamá +507 833 7346).\n\n"

    "REGLAS: NUNCA des precios ni menciones productos fuera de esta lista."
)


# ============================================================
# VERIFICACIÓN DEL WEBHOOK
# ============================================================

@app.get("/webhook")
async def verify_webhook(request: Request):

    params = request.query_params

    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(
            content=params.get("hub.challenge"),
            media_type="text/plain"
        )

    return Response(
        content="Token inválido",
        status_code=403
    )


# ============================================================
# WEBHOOK DE WHATSAPP
# ============================================================

@app.post("/webhook")
async def receive_webhook(request: Request):

    try:

        data = await request.json()

        # ----------------------------------------------------
        # Mostrar webhook completo para depuración
        # ----------------------------------------------------

        print("\n========== WEBHOOK RECIBIDO ==========")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("======================================\n")

        entry_list = data.get("entry", [])

        if not entry_list:
            return {"status": "ignored"}

        entry = entry_list[0]

        changes = entry.get("changes", [])

        if not changes:
            return {"status": "ignored"}

        change = changes[0]

        value = change.get("value", {})

        # ----------------------------------------------------
        # Ignorar eventos que no contienen mensajes
        # ----------------------------------------------------

        if "messages" not in value:
            print("Webhook recibido sin mensajes.")
            return {"status": "ignored"}

        messages = value.get("messages", [])

        if not messages:
            return {"status": "ignored"}

        message_obj = messages[0]

        # ----------------------------------------------------
        # DATOS DEL MENSAJE
        # ----------------------------------------------------

        message_type = message_obj.get("type")

        # Número tradicional
        phone_number = message_obj.get("from")

        # Nuevo identificador BSUID
        from_user_id = message_obj.get("from_user_id")

        # Algunas variantes pueden entregar el identificador
        # en otros campos relacionados
        from_parent_user_id = message_obj.get("from_parent_user_id")

        # ----------------------------------------------------
        # DATOS DEL CONTACTO
        # ----------------------------------------------------

        contacts = value.get("contacts", [])

        contact = contacts[0] if contacts else {}

        profile = contact.get("profile", {})

        # Nombre visible del perfil
        profile_name = profile.get("name")

        # Username nuevo de WhatsApp
        username = (
            profile.get("username")
            or contact.get("username")
            or contact.get("user_name")
        )

        # BSUID desde contacts
        contact_user_id = contact.get("user_id")

        # Número tradicional desde contacts
        wa_id = contact.get("wa_id")

        # ----------------------------------------------------
        # DETERMINAR IDENTIFICADOR PRINCIPAL
        # ----------------------------------------------------

        # IMPORTANTE:
        #
        # Si existe número, usamos el número.
        #
        # Si no existe número, usamos BSUID.
        #
        # Así funciona tanto con usuarios normales como
        # con usuarios que ocultan su número mediante username.

        recipient_id = (
            phone_number
            or wa_id
            or from_user_id
            or contact_user_id
        )

        if not recipient_id:
            print("ERROR: No se pudo obtener ningún identificador del usuario.")
            print("Mensaje recibido:", json.dumps(message_obj, indent=2, ensure_ascii=False))

            return {"status": "no_recipient"}

        # ----------------------------------------------------
        # IDENTIFICADOR PARA MEMORIA
        # ----------------------------------------------------

        # Preferimos BSUID porque es el identificador estable
        # asociado al usuario dentro del Business Portfolio.

        memory_id = (
            from_user_id
            or contact_user_id
            or phone_number
            or wa_id
        )

        # ----------------------------------------------------
        # INFORMACIÓN DEL CLIENTE
        # ----------------------------------------------------

        print("\n========== CLIENTE ==========")
        print("Nombre:", profile_name)
        print("Username:", username)
        print("Teléfono:", phone_number or wa_id)
        print("BSUID:", from_user_id or contact_user_id)
        print("ID utilizado para responder:", recipient_id)
        print("ID utilizado para memoria:", memory_id)
        print("=============================\n")

        # ----------------------------------------------------
        # SOLO PROCESAR MENSAJES DE TEXTO
        # ----------------------------------------------------

        if message_type != "text":

            print(
                f"Mensaje recibido pero no es texto. Tipo: {message_type}"
            )

            return {"status": "unsupported_message"}

        text_received = (
            message_obj
            .get("text", {})
            .get("body", "")
            .strip()
        )

        if not text_received:
            return {"status": "empty_message"}

        # ----------------------------------------------------
        # LOG DEL MENSAJE
        # ----------------------------------------------------

        display_name = (
            profile_name
            or username
            or phone_number
            or from_user_id
            or "Usuario"
        )

        print(
            f"Mensaje recibido de {display_name} "
            f"[ID: {recipient_id}]: {text_received}"
        )

        # ----------------------------------------------------
        # GEMINI
        # ----------------------------------------------------

        ai_response = ask_gemini_with_memory(
            memory_id,
            text_received
        )

        # ----------------------------------------------------
        # DERIVACIÓN COMERCIAL
        # ----------------------------------------------------

        if "[DERIVAR_VENTAS]" in ai_response:

            clean_response = (
                ai_response
                .replace("[DERIVAR_VENTAS]", "")
                .strip()
            )

            # -----------------------------------------------
            # RESPUESTA AL CLIENTE
            # -----------------------------------------------

            send_whatsapp_message(
                recipient_id,
                clean_response
            )

            # -----------------------------------------------
            # DATOS DEL CLIENTE PARA EL AGENTE
            # -----------------------------------------------

            cliente_identificacion = ""

            if profile_name:
                cliente_identificacion += (
                    f"👤 *Nombre:* {profile_name}\n"
                )

            if username:
                cliente_identificacion += (
                    f"🔹 *Username:* @{username}\n"
                )

            if phone_number or wa_id:
                cliente_identificacion += (
                    f"📱 *Número:* +{phone_number or wa_id}\n"
                )
            else:
                cliente_identificacion += (
                    "📱 *Número:* No disponible\n"
                )

            if from_user_id or contact_user_id:
                cliente_identificacion += (
                    f"🆔 *BSUID:* "
                    f"{from_user_id or contact_user_id}\n"
                )

            alerta_texto = (
                "🚨 *NUEVO LEAD / DERIVACIÓN COMERCIAL*\n\n"
                f"{cliente_identificacion}\n"
                f"💬 *Detalle e Interés:*\n"
                f"{clean_response}"
            )

            send_whatsapp_message(
                AGENTE_COMERCIAL_NUMBER,
                alerta_texto
            )

        else:

            # ------------------------------------------------
            # FLUJO NORMAL
            # ------------------------------------------------

            send_whatsapp_message(
                recipient_id,
                ai_response
            )

    except Exception as e:

        print(
            "ERROR al procesar webhook:",
            repr(e)
        )

    return {"status": "ok"}


# ============================================================
# GEMINI CON MEMORIA
# ============================================================

def ask_gemini_with_memory(
    user_id: str,
    user_prompt: str
) -> str:

    try:

        if user_id not in active_chats:

            print(
                f"Creando nueva conversación Gemini para: {user_id}"
            )

            active_chats[user_id] = ai_client.chats.create(
                model="gemini-3.6-flash",
                config={
                    "system_instruction": SYSTEM_INSTRUCTION_TEXT
                }
            )

        chat_session = active_chats[user_id]

        response = chat_session.send_message(
            user_prompt
        )

        return response.text

    except Exception as e:

        print(
            "Error detallado en Gemini con memoria:",
            repr(e)
        )

        # Si ocurre un error con la sesión,
        # eliminamos la sesión para poder reconstruirla
        # posteriormente.

        if user_id in active_chats:
            del active_chats[user_id]

        return (
            "Lo siento, tuve un breve inconveniente "
            "procesando tu mensaje. ¿Podrías repetirlo por favor?"
        )


# ============================================================
# ENVIAR MENSAJE A WHATSAPP
# ============================================================

def send_whatsapp_message(
    recipient_id: str,
    message_text: str
):

    # --------------------------------------------------------
    # Nunca intentar enviar a None
    # --------------------------------------------------------

    if not recipient_id:

        print(
            "ERROR: Intento de enviar mensaje sin destinatario."
        )

        return False

    if not message_text:

        print(
            "ERROR: Intento de enviar mensaje vacío."
        )

        return False

    url = (
        f"https://graph.facebook.com/v20.0/"
        f"{PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",

        # recipient_type ayuda a dejar explícito que
        # el destinatario es un usuario individual.
        "recipient_type": "individual",

        # IMPORTANTE:
        # 'to' puede ser número o BSUID dependiendo
        # del usuario.
        "to": recipient_id,

        "type": "text",

        "text": {
            "body": message_text
        }
    }

    try:

        res = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=20
        )

        print(
            "Respuesta Meta API para",
            recipient_id,
            ":",
            res.status_code
        )

        # Mostrar respuesta completa cuando hay error
        if res.status_code >= 400:

            print(
                "ERROR DE META:",
                res.text
            )

        return res.ok

    except requests.RequestException as e:

        print(
            "ERROR DE CONEXIÓN CON META:",
            repr(e)
        )

        return False
```

