import os
import json
import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel, ConfigDict # ### NOVO ### Importa ConfigDict
from sqlalchemy.orm import Session
from typing import List # ### NOVO ### Para tipagem de listas na resposta

from fastapi.middleware.cors import CORSMiddleware

from database import crud, models
from database.database import engine, get_db

models.Base.metadata.create_all(bind=engine )



# ... outros imports
from database.database import engine, get_db

# ### NOVO ###
# Apaga todas as tabelas existentes (CUIDADO: ISSO DELETA TODOS OS DADOS)
# E depois as recria. Faremos isso apenas uma vez para limpar o banco.

models.Base.metadata.create_all(bind=engine)

# --- Configuração Inicial ---
# ... o resto do código continua igual


# --- Configuração ---
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
ALERT_KEYWORDS = ["dor", "febre", "difícil", "não tomei", "sem dormir", "ansioso", "triste"]

app = FastAPI(
    title="Cuide.me Backend",
    description="API para o Sistema de Acompanhamento Inteligente de Pacientes.",
    version="0.3.0" # ### MUDANÇA ### Nova versão
)

# --- Configuração do CORS ---
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

# ### NOVO - INÍCIO ###
# --- Modelos Pydantic para Respostas da API ---
# Isso define a "forma" dos dados que nossa API enviará para o frontend.

class PatientResponse(BaseModel):
    id: int
    phone_number: str
    name: str | None = None
    has_alert: bool = False # Novo campo!

    # Configuração para permitir que o Pydantic leia dados de objetos SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

class MessageResponse(BaseModel):
    id: int
    text: str
    sender: str
    timestamp: str # Simplificando para string na resposta

    model_config = ConfigDict(from_attributes=True)

# ### NOVO - FIM ###


# --- Webhook do WhatsApp (sem alterações) ---
@app.post("/webhook")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    # ... (Todo o código do webhook continua exatamente igual)
    data = await request.json()
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
            crud.create_message(db, patient_id=patient.id, text=message_text, has_alert=has_alert)
            print(f"Mensagem de {from_number} salva para o paciente {patient.id} com alerta: {has_alert}")
        return {"status": "ok"}
    except Exception as e:
        print(f"Erro ao processar a mensagem: {e}")
        return {"status": "error", "detail": str(e)}


# ### MUDANÇA - INÍCIO ###
# --- Endpoints da API para o Frontend ---

@app.get("/api/patients", response_model=List[PatientResponse])
def get_patients(db: Session = Depends(get_db)):
    """
    Retorna uma lista de todos os pacientes, verificando se cada um
    tem alguma mensagem com alerta.
    """
    all_patients = db.query(models.Patient).all()
    
    # Cria a lista de resposta
    response_patients = []
    for patient in all_patients:
        # Verifica se existe QUALQUER mensagem para este paciente com has_alert = True
        has_alert = db.query(models.Message).filter(
            models.Message.patient_id == patient.id,
            models.Message.has_alert == True
        ).first() is not None # .first() is not None é uma forma eficiente de checar existência

        response_patients.append({
            "id": patient.id,
            "phone_number": patient.phone_number,
            "name": patient.name,
            "has_alert": has_alert # Adiciona o resultado da verificação
        })
        
    return response_patients

@app.get("/api/messages/{patient_id}")
def get_messages_for_patient(patient_id: int, db: Session = Depends(get_db)):
    """
    Busca todas as mensagens de um paciente, retorna os dados e, em seguida,
    marca os alertas como lidos no banco de dados.
    """
    # 1. Busca os objetos de mensagem do banco de dados.
    messages_from_db = db.query(models.Message).filter(
        models.Message.patient_id == patient_id
    ).order_by(models.Message.timestamp.asc()).all()

    # 2. ### A CORREÇÃO CRÍTICA ###
    # Converte manualmente os objetos do SQLAlchemy para um dicionário Python simples.
    # Isso garante que o FastAPI possa lê-los e transformá-los em JSON corretamente.
    response_data = [
        {
            "id": msg.id,
            "text": msg.text,
            "sender": msg.sender,
            "timestamp": msg.timestamp.isoformat() # .isoformat() converte o objeto de data para texto
        }
        for msg in messages_from_db
    ]

    # 3. Agora que já preparamos a resposta, atualizamos o banco de dados.
    # Esta operação não afetará a 'response_data' que já está na memória.
    db.query(models.Message).filter(
        models.Message.patient_id == patient_id,
        models.Message.has_alert == True
    ).update({"has_alert": False}, synchronize_session=False)
    db.commit()
    
    # 4. Retorna a lista de dicionários, que o FastAPI converterá em JSON.
    return response_data


# ### MUDANÇA - FIM ###

# --- Endpoints de verificação (sem alterações) ---
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

# Adicione este código antes do @app.get("/")

# ### NOVO - INÍCIO (Alternativa Gratuita para Cron Job) ###
from fastapi import Header, HTTPException
from typing import Annotated
from send_scheduled_messages import run_task # Importa nossa função de envio

# Carrega o token secreto que vamos configurar no Render
CRON_SECRET = os.getenv("CRON_SECRET")

@app.post("/trigger-daily-task")
async def trigger_task(
    x_cron_secret: Annotated[str | None, Header()] = None
):
    """
    Endpoint secreto para ser chamado pelo GitHub Actions.
    Ele executa a tarefa de envio de mensagens.
    """
    print("Endpoint /trigger-daily-task chamado.")
    if not CRON_SECRET or x_cron_secret != CRON_SECRET:
        print("ERRO: Token secreto do Cron inválido ou ausente.")
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    print("Token secreto validado. Iniciando a tarefa em segundo plano...")
    # Idealmente, isso rodaria em background, mas para o MVP vamos rodar direto.
    run_task()
    
    return {"status": "Task triggered successfully"}

# ### NOVO - FIM ###