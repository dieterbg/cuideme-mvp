import os
import httpx
from sqlalchemy.orm import Session
from database.database import SessionLocal
from database import crud, models

# Carrega as variáveis de ambiente necessárias para a API do WhatsApp
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN" )
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
# Garante que a versão da API do Graph seja uma mais recente
WHATSAPP_API_URL = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

# Mensagem que será enviada aos pacientes
# IMPORTANTE: Para um ambiente de produção, esta mensagem precisa ser um "Template"
# pré-aprovado pela Meta. Para nosso número de teste, podemos enviar texto livre.
MESSAGE_TO_SEND = "Olá! Este é um lembrete automático do Cuide.me. Como você está se sentindo hoje?"

def send_whatsapp_message(phone_number: str, message: str ):
    """
    Função que envia uma mensagem de texto para um número de WhatsApp específico.
    """
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": message},
    }
    
    try:
        with httpx.Client( ) as client:
            response = client.post(WHATSAPP_API_URL, json=payload, headers=headers)
            response.raise_for_status()  # Lança um erro se a resposta for 4xx ou 5xx
        
        print(f"Mensagem enviada com sucesso para {phone_number}. Status: {response.status_code}")
        return True
    except httpx.HTTPStatusError as e:
        print(f"Erro ao enviar mensagem para {phone_number}: {e.response.status_code}" )
        print(f"Detalhe do erro: {e.response.text}")
        return False
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")
        return False

def run_task():
    """
    Função principal do script: busca todos os pacientes e envia a mensagem para cada um.
    """
    print("--- INICIANDO TAREFA DE ENVIO DE MENSAGENS PROGRAMADAS ---")
    
    # Cria uma sessão com o banco de dados
    db: Session = SessionLocal()
    
    try:
        patients = crud.get_all_patients(db)
        if not patients:
            print("Nenhum paciente encontrado no banco de dados. Tarefa encerrada.")
            return

        print(f"Encontrados {len(patients)} pacientes. Iniciando envios...")
        
        success_count = 0
        failure_count = 0

        for patient in patients:
            # Adiciona uma verificação para não enviar para si mesmo se não quiser
            # if patient.phone_number == "SEU_NUMERO_DE_TESTE": continue
            if send_whatsapp_message(patient.phone_number, MESSAGE_TO_SEND):
                success_count += 1
            else:
                failure_count += 1
        
        print("--- TAREFA CONCLUÍDA ---")
        print(f"Resumo: {success_count} mensagens enviadas com sucesso, {failure_count} falhas.")

    finally:
        # Garante que a conexão com o banco de dados seja sempre fechada
        db.close()

if __name__ == "__main__":
    run_task()
