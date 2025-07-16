import os
import json
import httpx
from fastapi import FastAPI, Request, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from typing import List, Annotated
import google.generativeai as genai 

# NOVOS IMPORTS
from passlib.context import CryptContext

from fastapi.middleware.cors import CORSMiddleware
from database import crud, models
from database.database import engine, get_db
from send_scheduled_messages import run_task

# ... (ConnectionManager e models.Base permanecem os mesmos)
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}
    async def connect(self, websocket: WebSocket, patient_id: int):
        await websocket.accept()
        if patient_id not in self.active_connections:
            self.active_connections[patient_id] = []
        self.active_connections[patient_id].append(websocket)
        print(f"Nova conexão WebSocket para o paciente {patient_id}.")
    def disconnect(self, websocket: WebSocket, patient_id: int):
        if patient_id in self.active_connections:
            self.active_connections[patient_id].remove(websocket)
            if not self.active_connections[patient_id]:
                del self.active_connections[patient_id]
            print(f"Conexão WebSocket fechada para o paciente {patient_id}.")
    async def broadcast_to_patient_viewers(self, patient_id: int, message: dict):
        if patient_id in self.active_connections:
            for connection in self.active_connections[patient_id]:
                await connection.send_json(message)
                print(f"Mensagem enviada via WebSocket para observadores do paciente {patient_id}.")

manager = ConnectionManager()
models.Base.metadata.create_all(bind=engine)

# ... (Variáveis de ambiente e cliente AI permanecem os mesmos)
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
CRON_SECRET = os.getenv("CRON_SECRET")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    print("AVISO: Chave da API do Google não encontrada. A funcionalidade de IA estará desativada.")

# ### NOVA SEÇÃO DE SEGURANÇA ###
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)
# ################################

ALERT_KEYWORDS = ["dor", "febre", "difícil", "não tomei", "sem dormir", "ansioso", "triste"]

app = FastAPI(
    title="Cuide.me Backend",
    description="API para o Sistema de Acompanhamento Inteligente de Pacientes.",
    version="0.8.0" # Versão incrementada
)

# ... (CORS permanece o mesmo)
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

# ### NOVOS MODELOS PYDANTIC (SCHEMAS) ###
class ProfessionalCreate(BaseModel):
    email: str
    password: str

class ProfessionalResponse(BaseModel):
    id: int
    email: str
    model_config = ConfigDict(from_attributes=True)
# ######################################

class MessageSendRequest(BaseModel):
    text: str
class PatientResponse(BaseModel):
    id: int
    phone_number: str
    name: str | None = None
    has_alert: bool = False
    status: str
    model_config = ConfigDict(from_attributes=True)

# ... (Função send_whatsapp_message permanece a mesma)
def send_whatsapp_message(to_number: str, text: str):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to_number, "type": "text", "text": {"body": text}}
    try:
        with httpx.Client() as http_client:
            response = http_client.post(url, headers=headers, json=data)
            response.raise_for_status()
        print(f"Mensagem enviada com sucesso para {to_number}.")
        return True
    except httpx.HTTPStatusError as e:
        print(f"Erro ao enviar mensagem para {to_number}: {e.response.status_code}"); print(f"Detalhe do erro: {e.response.text}")
        return False


# ### NOVO ENDPOINT DE REGISTRO ###
@app.post("/auth/register", response_model=ProfessionalResponse, status_code=201)
def register_professional(professional: ProfessionalCreate, db: Session = Depends(get_db)):
    db_professional = crud.get_professional_by_email(db, email=professional.email)
    if db_professional:
        raise HTTPException(status_code=400, detail="Email já registrado")
    
    hashed_password = get_password_hash(professional.password)
    return crud.create_professional(db=db, email=professional.email, hashed_password=hashed_password)
# ################################

# ... (Todos os outros endpoints de /webhook até o final permanecem os mesmos)
# (Cole aqui o restante dos seus endpoints, de /webhook até o final)
@app.post("/webhook")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    try:
        if (data.get("entry") and data["entry"][0].get("changes") and data["entry"][0]["changes"][0].get("value") and data["entry"][0]["changes"][0]["value"].get("messages")):
            message_data = data["entry"][0]["changes"][0]["value"]["messages"][0]
            from_number = message_data["from"]
            message_text = message_data["text"]["body"]
            patient = crud.get_or_create_patient(db, phone_number=from_number)
            lower_message_text = message_text.lower()
            found_keywords = [keyword for keyword in ALERT_KEYWORDS if keyword in lower_message_text]
            has_alert = bool(found_keywords)
            new_message = crud.create_message(db, patient_id=patient.id, text=message_text, has_alert=has_alert, sender="patient")
            message_dict = { "id": new_message.id, "text": new_message.text, "sender": new_message.sender, "timestamp": new_message.timestamp.isoformat() }
            await manager.broadcast_to_patient_viewers(patient.id, message_dict)
            if not has_alert and patient.status == 'automatico' and GOOGLE_API_KEY:
                system_prompt = ("Você é um assistente de saúde. Analise a mensagem de um paciente. Sua tarefa é decidir se uma resposta automática de apoio é apropriada. Responda APENAS com um objeto JSON. Se a mensagem for uma simples atualização, um agradecimento ou uma afirmação positiva, retorne: {\"responder\": true, \"texto_resposta\": \"[uma frase curta de apoio]\"}. Exemplos de frases: 'Obrigado por compartilhar!', 'Entendido, continue assim!', 'Registro feito!'. Se a mensagem for uma pergunta, um pedido de ajuda, uma queixa (mesmo que sutil), ou qualquer coisa que exija atenção humana, retorne: {\"responder\": false}")
                user_prompt = f"Analise esta mensagem do paciente: \"{message_text}\""
                try:
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    response = model.generate_content(prompt) # Corrigido para usar a variável prompt correta
                    ai_decision = json.loads(response.text)
                    if ai_decision.get("responder") is True and (response_text := ai_decision.get("texto_resposta")):
                        print(f"IA decidiu responder ao paciente {patient.id} com: '{response_text}'")
                        send_whatsapp_message(to_number=patient.phone_number, text=response_text)
                except Exception as e: print(f"Erro ao processar resposta da IA: {e}")
        return {"status": "ok"}
    except Exception as e:
        print(f"Erro fatal ao processar o webhook: {e}")
        return {"status": "error", "detail": str(e)}

@app.websocket("/ws/{patient_id}")
async def websocket_endpoint(websocket: WebSocket, patient_id: int):
    await manager.connect(websocket, patient_id)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: manager.disconnect(websocket, patient_id)

@app.get("/api/patients", response_model=List[PatientResponse])
def get_patients(db: Session = Depends(get_db)):
    all_patients = db.query(models.Patient).all()
    response_patients = []
    for patient in all_patients:
        has_alert = db.query(models.Message).filter(models.Message.patient_id == patient.id, models.Message.has_alert == True).first() is not None
        response_patients.append({"id": patient.id, "phone_number": patient.phone_number, "name": patient.name, "has_alert": has_alert, "status": patient.status})
    return response_patients

@app.get("/api/messages/{patient_id}")
def get_messages_for_patient(patient_id: int, db: Session = Depends(get_db)):
    messages_from_db = db.query(models.Message).filter(models.Message.patient_id == patient_id).order_by(models.Message.timestamp.asc()).all()
    response_data = [{"id": msg.id, "text": msg.text, "sender": msg.sender, "timestamp": msg.timestamp.isoformat()} for msg in messages_from_db]
    db.query(models.Message).filter(models.Message.patient_id == patient_id, models.Message.has_alert == True).update({"has_alert": False}, synchronize_session=False)
    db.commit()
    return response_data

@app.post("/api/patients/{patient_id}/assume-control", status_code=200)
def assume_conversation_control(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient: raise HTTPException(status_code=404, detail="Paciente não encontrado")
    patient.status = "manual"; db.commit(); return {"status": "success", "message": "Controle manual ativado."}

@app.post("/api/patients/{patient_id}/release-control", status_code=200)
def release_conversation_control(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient: raise HTTPException(status_code=404, detail="Paciente não encontrado")
    patient.status = "automatico"; db.commit(); return {"status": "success", "message": "Controle automático reativado."}

@app.post("/api/messages/send/{patient_id}", status_code=201)
def send_message_to_patient(patient_id: int, message_request: MessageSendRequest, db: Session = Depends(get_db)):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient: raise HTTPException(status_code=404, detail="Paciente não encontrado")
    if not send_whatsapp_message(to_number=patient.phone_number, text=message_request.text):
        raise HTTPException(status_code=500, detail="Erro ao enviar mensagem pela API do WhatsApp.")
    new_message = crud.create_message(db=db, patient_id=patient.id, text=message_request.text, sender="professional", has_alert=False)
    return {"id": new_message.id, "text": new_message.text, "sender": new_message.sender, "timestamp": new_message.timestamp.isoformat()}

@app.post("/api/messages/{patient_id}/summarize")
def summarize_conversation(patient_id: int, db: Session = Depends(get_db)):
    if not GOOGLE_API_KEY: raise HTTPException(status_code=503, detail="A funcionalidade de IA não está configurada no servidor.")
    messages = db.query(models.Message).filter(models.Message.patient_id == patient_id).order_by(models.Message.timestamp.asc()).all()
    if not messages: raise HTTPException(status_code=404, detail="Nenhuma mensagem encontrada para este paciente.")
    conversation_text = ""
    for msg in messages:
        sender_name = "Profissional" if msg.sender == 'professional' else "Paciente"
        conversation_text += f"{sender_name}: {msg.text}\n"
    prompt = ("Você é um assistente de saúde inteligente. Sua tarefa é resumir a seguinte conversa entre um paciente em tratamento e um profissional de saúde para que o profissional possa entender rapidamente o estado do paciente. O resumo deve ser conciso e útil.\n\n"
        "Por favor, resuma a conversa abaixo em bullet points, focando em: "
        "1. Evolução de sintomas ou queixas. "
        "2. Adesão ao tratamento (medicamentos, dieta, exercícios). "
        "3. Efeitos colaterais mencionados. "
        "4. Estado emocional ou humor geral relatado. "
        "5. Dados numéricos específicos reportados (peso, pressão, etc.).\n\n"
        "Seja direto ao ponto e não invente informações que não estão na conversa.\n\n"
        f"--- CONVERSA ---\n{conversation_text}"
        "\n--- RESUMO ---")
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        summary = response.text; return {"summary": summary}
    except Exception as e:
        print(f"Erro na API do Google Gemini: {e}"); raise HTTPException(status_code=500, detail="Ocorreu um erro ao gerar o resumo.")

@app.post("/trigger-daily-task")
async def trigger_task(x_cron_secret: Annotated[str | None, Header()] = None):
    if not CRON_SECRET or x_cron_secret != CRON_SECRET: raise HTTPException(status_code=401, detail="Unauthorized")
    run_task(); return {"status": "Task triggered successfully"}

@app.get("/")
def read_root(): return {"status": "API do Cuide.me está funcionando!"}

@app.get("/webhook")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode"); token = request.query_params.get("hub.verify_token"); challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN: return int(challenge)
    else: raise HTTPException(status_code=403, detail="Verification token mismatch")