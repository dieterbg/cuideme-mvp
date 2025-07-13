import os
import json
import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

# ### NOVO - INÍCIO ###
from fastapi.middleware.cors import CORSMiddleware
# ### NOVO - FIM ###

from database import crud, models
from database.database import engine, get_db

models.Base.metadata.create_all(bind=engine )

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

ALERT_KEYWORDS = ["dor", "febre", "difícil", "não tomei", "sem dormir", "ansioso", "triste"]

app = FastAPI(
    title="Cuide.me MVP Backend",
    description="API para receber e processar mensagens do WhatsApp.",
    version="0.2.1"
)

# ### NOVO - INÍCIO ###
# Configuração do CORS - A "Lista de Visitantes Autorizados"
origins = [
    "https://cuideme-painel.onrender.com", # Endereço do seu painel
    "http://localhost:5173",             # Endereço para testes futuros no seu PC
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, # Permite apenas os endereços da lista 'origins'
    allow_credentials=True,
    allow_methods=["*"],   # Permite todos os tipos de pedido (GET, POST, etc )
    allow_headers=["*"],   # Permite todos os cabeçalhos no pedido
)
# ### NOVO - FIM ###

# --- O resto do arquivo continua igual ---

@app.get("/")
def read_root():
    return {"status": "API do Cuide.me (Fase 2) está funcionando!"}

# ... (cole o resto do seu main.py aqui)
@app.get("/webhook")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print(f"WEBHOOK_VERIFIED")
        return int(challenge)
    else:
        print("ERRO DE VERIFICAÇÃO DO WEBHOOK")
        raise HTTPException(status_code=403, detail="Verification token mismatch")

@app.post("/webhook")
async def handle_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    data = await request.json()
    print("--- MENSAGEM RECEBIDA ---")
    print(json.dumps(data, indent=2))

    try:
        if (
            data.get("entry") and
            data["entry"][0].get("changes") and
            data["entry"][0]["changes"][0].get("value") and
            data["entry"][0]["changes"][0]["value"].get("messages")
        ):
            message_data = data["entry"][0]["changes"][0]["value"]["messages"][0]
            from_number = message_data["from"]
            message_text = message_data["text"]["body"]

            print(f"Mensagem de {from_number}: {message_text}")

            patient = crud.get_or_create_patient(db, phone_number=from_number)
            print(f"Paciente ID {patient.id} ({patient.phone_number}) identificado/criado.")

            lower_message_text = message_text.lower()
            found_keywords = [keyword for keyword in ALERT_KEYWORDS if keyword in lower_message_text]
            has_alert = bool(found_keywords)

            if has_alert:
                print(f"!!! ALERTA GERADO !!! Motivo: {', '.join(found_keywords)}")

            crud.create_message(db, patient_id=patient.id, text=message_text, has_alert=has_alert)
            print(f"Mensagem salva no banco de dados com status de alerta: {has_alert}")

        return {"status": "ok"}

    except Exception as e:
        print(f"Erro ao processar a mensagem: {e}")
        return {"status": "error", "detail": str(e)}

@app.get("/api/patients")
def get_patients(db: Session = Depends(get_db)):
    patients = db.query(models.Patient).all()
    return patients

@app.get("/api/messages/{patient_id}")
def get_messages_for_patient(patient_id: int, db: Session = Depends(get_db)):
    messages = db.query(models.Message).filter(models.Message.patient_id == patient_id).order_by(models.Message.timestamp.asc()).all()
    if not messages:
      return []
    return messages
