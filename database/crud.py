from sqlalchemy.orm import Session
from . import models

def get_or_create_patient(db: Session, phone_number: str):
    """
    Busca um paciente pelo número de telefone. Se não existir, cria um novo.
    """
    patient = db.query(models.Patient).filter(models.Patient.phone_number == phone_number).first()
    if not patient:
        patient = models.Patient(phone_number=phone_number)
        db.add(patient)
        db.commit()
        db.refresh(patient)
    return patient

# ### FUNÇÃO CORRIGIDA ###
def create_message(db: Session, patient_id: int, text: str, has_alert: bool, sender: str = "patient"):
    """
    Cria e salva uma nova mensagem no banco de dados.
    O parâmetro 'sender' agora é aceito. O valor padrão é 'patient'.
    """
    db_message = models.Message(
        patient_id=patient_id,
        text=text,
        has_alert=has_alert,
        sender=sender  # A linha que usa o novo argumento
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message

def get_all_patients(db: Session):
    """
    Retorna todos os pacientes do banco de dados.
    """
    return db.query(models.Patient).all()
