import os
import json
import httpx
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from typing import List, Annotated

# Importa o middleware de CORS para permitir a comunicação com o frontend
from fastapi.middleware.cors import CORSMiddleware

# Importa nossos módulos de banco de dados
from database import crud, models
from database.database import engine, get_db

# Importa a função de envio de mensagens do nosso script de automação
from send_scheduled_messages import run_task

# --- Inicialização do Banco de Dados ---
# Esta linha cria as tabelas no banco de dados (patients, messages ) se elas não existirem.
# O Render executará isso sempre que o serviço for iniciado.
models.Base.metadata.create_all(bind=engine)


# --- Configuração das Variáveis de Ambiente ---
# Carrega os segredos configurados no ambiente do Render
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
CRON_SECRET = os.getenv("CRON_SECRET") # Token para proteger o endpoint do Cron Job

# Palavras-chave para o sistema de alerta simples
ALERT_KEYWORDS = ["dor", "febre", "difícil", "não tomei", "sem dormir", "ansioso", "triste"]


# --- Inicialização do Aplicativo FastAPI ---
app = FastAPI(
    title="Cuide.me Backend",
    description="API para o Sistema de Acompanhamento Inteligente de Pacientes.",
    version="0.3.0"
)


# --- Configuração do CORS ---
# Define quais origens (sites) têm permissão para acessar esta API.
origins = [
    "https://cuideme-painel.onrender.com", # URL do nosso frontend de produção
    "http://localhost:5173",             # URL para desenvolvimento local do frontend
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
 )


# --- Modelos Pydantic para Respostas da API ---
# Definem a "forma" dos dados que nossa API enviará para o frontend, garantindo consistência.

class PatientResponse(BaseModel):
    id: int
    phone_number: str
    name: str | None = None
    has_alert: bool = False
    status: str # 'automatico' ou 'manual'

    # Configuração para permitir que o Pydantic leia dados de objetos SQLAlchemy
    model_config = ConfigDict(from_attributes=True)


# --- Webhook do WhatsApp ---
# Este endpoint é o ponto de entrada para todas as mensagens enviadas pelos pacientes.
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

            # 1. Encontra ou cria o paciente no banco de dados
            patient = crud.get_or_create_patient(db, phone_number=from_number)
            print(f"Paciente ID {patient.id} ({patient.phone_number}) identificado/criado.")

            # 2. Analisa a mensagem em busca de alertas
            lower_message_text = message_text.lower()
            found_keywords = [keyword for keyword in ALERT_KEYWORDS if keyword in lower_message_text]
            has_alert = bool(found_keywords)

            if has_alert:
                print(f"!!! ALERTA GERADO !!! Motivo: {', '.join(found_keywords)}")

            # 3. Salva a mensagem no banco de dados
            crud.create_message(db, patient_id=patient.id, text=message_text, has_alert=has_alert)
            print(f"Mensagem salva no banco de dados com status de alerta: {has_alert}")

        return {"status": "ok"}
    except Exception as e:
        print(f"Erro ao processar a mensagem: {e}")
        return {"status": "error", "detail": str(e)}


# --- Endpoints da API para o Frontend ---

@app.get("/api/patients", response_model=List[PatientResponse])
def get_patients(db: Session = Depends(get_db)):
    """ Retorna uma lista de todos os pacientes, incluindo o status de alerta e de controle. """
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
    """ Busca as mensagens de um paciente e marca os alertas como lidos. """
    messages_from_db = db.query(models.Message).filter(models.Message.patient_id == patient_id).order_by(models.Message.timestamp.asc()).all()

    response_data = [
        {"id": msg.id, "text": msg.text, "sender": msg.sender, "timestamp": msg.timestamp.isoformat()}
        for msg in messages_from_db
    ]

    # Marca os alertas como "lidos" após a busca
    db.query(models.Message).filter(
        models.Message.patient_id == patient_id,
        models.Message.has_alert == True
    ).update({"has_alert": False}, synchronize_session=False)
    db.commit()
    
    return response_data


# --- Endpoints de Controle da Conversa ---

@app.post("/api/patients/{patient_id}/assume-control", status_code=200)
def assume_conversation_control(patient_id: int, db: Session = Depends(get_db)):
    """ Muda o status do paciente para 'manual'. """
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
    
    patient.status = "manual"
    db.commit()
    print(f"Controle da conversa assumido para o paciente {patient_id}. Status: manual.")
    return {"status": "success", "message": "Controle manual ativado."}

@app.post("/api/patients/{patient_id}/release-control", status_code=200)
def release_conversation_control(patient_id: int, db: Session = Depends(get_db)):
    """ Muda o status do paciente de volta para 'automatico'. """
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
        
    patient.status = "automatico"
    db.commit()
    print(f"Controle da conversa liberado para o paciente {patient_id}. Status: automatico.")
    return {"status": "success", "message": "Controle automático reativado."}


# --- Endpoint para Disparo da Tarefa Agendada ---

@app.post("/trigger-daily-task")
async def trigger_task(x_cron_secret: Annotated[str | None, Header()] = None):
    """ Endpoint secreto para ser chamado pelo GitHub Actions para executar a tarefa de envio. """
    print("Endpoint /trigger-daily-task chamado.")
    if not CRON_SECRET or x_cron_secret != CRON_SECRET:
        print("ERRO: Token secreto do Cron inválido ou ausente.")
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    print("Token secreto validado. Iniciando a tarefa...")
    run_task()
    return {"status": "Task triggered successfully"}


# --- Endpoints de Verificação ---

@app.get("/")
def read_root():
    """ Endpoint inicial para verificar se a API está no ar. """
    return {"status": "API do Cuide.me (Fase 3) está funcionando!"}

@app.get("/webhook")
def verify_webhook(request: Request):
    """ Endpoint usado pelo WhatsApp para verificar a autenticidade do webhook. """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("WEBHOOK_VERIFIED")
        return int(challenge)
    else:
        print("ERRO DE VERIFICAÇÃO DO WEBHOOK")
        raise HTTPException(status_code=403, detail="Verification token mismatch")

