import os
import json
import httpx
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from typing import List, Annotated

from fastapi.middleware.cors import CORSMiddleware
from database import crud, models
from database.database import engine, get_db
from send_scheduled_messages import run_task

models.Base.metadata.create_all(bind=engine )

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
CRON_SECRET = os.getenv("CRON_SECRET")

ALERT_KEYWORDS = ["dor", "febre", "difícil", "não tomei", "sem dormir", "ansioso", "triste"]

app = FastAPI(
    title="Cuide.me Backend",
    description="API para o Sistema de Acompanhamento Inteligente de Pacientes.",
    version="0.3.1" # Versão incrementada
)

origins = [
    "https://cuideme-painel.onrender.com",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
 )

class MessageSendRequest(BaseModel):
    text: str

class PatientResponse(BaseModel):
    id: int
    phone_number: str
    name: str | None = None
    has_alert: bool = False
    status: str
    model_config = ConfigDict(from_attributes=True)

@app.post("/webhook")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
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
            patient = crud.get_or_create_patient(db, phone_number=from_number)
            lower_message_text = message_text.lower()
            found_keywords = [keyword for keyword in ALERT_KEYWORDS if keyword in lower_message_text]
            has_alert = bool(found_keywords)
            crud.create_message(db, patient_id=patient.id, text=message_text, has_alert=has_alert, sender="patient") # Garante que o remetente é 'patient'
        return {"status": "ok"}
    except Exception as e:
        print(f"Erro ao processar a mensagem: {e}")
        return {"status": "error", "detail": str(e)}

@app.get("/api/patients", response_model=List[PatientResponse])
def get_patients(db: Session = Depends(get_db)):
    all_patients = db.query(models.Patient).all()
    response_patients = []
    for patient in all_patients:
        has_alert = db.query(models.Message).filter(
            models.Message.patient_id == patient.id,
            models.Message.has_alert == True
        ).first() is not None
        response_patients.append({
            "id": patient.id,
            "phone_number": patient.phone_number,
            "name": patient.name,
            "has_alert": has_alert,
            "status": patient.status
        })
    return response_patients

@app.get("/api/messages/{patient_id}")
def get_messages_for_patient(patient_id: int, db: Session = Depends(get_db)):
    messages_from_db = db.query(models.Message).filter(models.Message.patient_id == patient_id).order_by(models.Message.timestamp.asc()).all()
    response_data = [
        {"id": msg.id, "text": msg.text, "sender": msg.sender, "timestamp": msg.timestamp.isoformat()}
        for msg in messages_from_db
    ]
    db.query(models.Message).filter(
        models.Message.patient_id == patient_id,
        models.Message.has_alert == True
    ).update({"has_alert": False}, synchronize_session=False)
    db.commit()
    return response_data

@app.post("/api/patients/{patient_id}/assume-control", status_code=200)
def assume_conversation_control(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
    patient.status = "manual"
    db.commit()
    return {"status": "success", "message": "Controle manual ativado."}

@app.post("/api/patients/{patient_id}/release-control", status_code=200)
def release_conversation_control(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
    patient.status = "automatico"
    db.commit()
    return {"status": "success", "message": "Controle automático reativado."}

# ### ENDPOINT DE ENVIO CORRIGIDO ###
@app.post("/api/messages/send/{patient_id}", status_code=201)
def send_message_to_patient(patient_id: int, message_request: MessageSendRequest, db: Session = Depends(get_db)):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": patient.phone_number, "type": "text", "text": {"body": message_request.text}}

    try:
        with httpx.Client( ) as client:
            response = client.post(url, headers=headers, json=data)
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        print(f"Erro ao enviar mensagem para {patient.phone_number}: {e.response.status_code}" )
        print(f"Detalhe do erro: {e.response.text}")
        raise HTTPException(status_code=500, detail=f"Erro na API do WhatsApp: {e.response.text}")

    # A CORREÇÃO ESTÁ AQUI:
    # Garantimos que a mensagem é salva com o remetente 'professional'
    new_message = crud.create_message(
        db=db,
        patient_id=patient.id,
        text=message_request.text,
        sender="professional", # Marcamos explicitamente o remetente
        has_alert=False # Mensagens do profissional não geram alerta
    )
    print(f"Mensagem do profissional para o paciente {patient.id} salva no banco.")
    
    # Retornamos um dicionário com os dados da mensagem para o frontend
    return {
        "id": new_message.id,
        "text": new_message.text,
        "sender": new_message.sender,
        "timestamp": new_message.timestamp.isoformat()
    }

@app.post("/trigger-daily-task")
async def trigger_task(x_cron_secret: Annotated[str | None, Header()] = None):
    if not CRON_SECRET or x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    run_task()
    return {"status": "Task triggered successfully"}

@app.get("/")
def read_root():
    return {"status": "API do Cuide.me (Fase 3) está funcionando!"}

@app.get("/webhook")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)
    else:
        raise HTTPException(status_code=403, detail="Verification token mismatch")
