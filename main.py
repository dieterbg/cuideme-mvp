import os
import json
import httpx
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel

# --- Configuração Inicial ---
# Carrega as variáveis de ambiente. O Render vai injetar essas variáveis.
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN" )
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# Palavras-chave que disparam um alerta. Simples para o MVP.
ALERT_KEYWORDS = ["dor", "febre", "difícil", "não tomei", "sem dormir", "ansioso", "triste"]

# Inicializa o aplicativo FastAPI
app = FastAPI(
    title="Cuide.me MVP Backend",
    description="API para receber e processar mensagens do WhatsApp.",
    version="0.1.0"
)

# --- Modelos de Dados (Pydantic) ---
# Isso ajuda o FastAPI a validar os dados que chegam do WhatsApp.
class WebhookRequest(BaseModel):
    object: str
    entry: list

# --- Endpoints da API ---

@app.get("/")
def read_root():
    """ Endpoint inicial para verificar se a API está no ar. """
    return {"status": "API do Cuide.me está funcionando!"}

@app.get("/webhook")
def verify_webhook(
    request: Request
):
    """
    Este endpoint é usado pelo WhatsApp para verificar a autenticidade do seu webhook.
    Ele espera um 'hub.verify_token' e responde com o 'hub.challenge'.
    """
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
    request: Request
):
    """
    Este endpoint recebe as mensagens dos pacientes via WhatsApp.
    """
    data = await request.json()
    print("--- MENSAGEM RECEBIDA ---")
    print(json.dumps(data, indent=2)) # Imprime o corpo da requisição para depuração

    # Extrai a mensagem do corpo da requisição do WhatsApp
    try:
        if (
            data.get("entry") and
            data["entry"][0].get("changes") and
            data["entry"][0]["changes"][0].get("value") and
            data["entry"][0]["changes"][0]["value"].get("messages")
        ):
            message_data = data["entry"][0]["changes"][0]["value"]["messages"][0]
            from_number = message_data["from"]
            message_text = message_data["text"]["body"].lower() # Converte para minúsculas

            print(f"Mensagem de {from_number}: {message_text}")

            # Lógica de Alerta Simples (MVP)
            found_keywords = [keyword for keyword in ALERT_KEYWORDS if keyword in message_text]

            if found_keywords:
                # Se encontrar palavras-chave, um alerta é gerado.
                # No MVP, vamos apenas imprimir no console.
                # Na Fase 2, isso enviaria um alerta para o painel.
                print(f"!!! ALERTA GERADO !!! Paciente: {from_number}. Motivo: {', '.join(found_keywords)}")
                # TODO: Salvar alerta no banco de dados.
            else:
                print("Mensagem recebida sem alertas.")

            # TODO: Salvar a mensagem no banco de dados.

        return {"status": "ok"}

    except Exception as e:
        print(f"Erro ao processar a mensagem: {e}")
        return {"status": "error", "detail": str(e)}
