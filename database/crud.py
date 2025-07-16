from sqlalchemy.orm import Session
from . import models

# ... (funções existentes get_or_create_patient, create_message, get_all_patients) ...
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

def create_message(db: Session, patient_id: int, text: str, has_alert: bool, sender: str = "patient"):
    """
    Cria e salva uma nova mensagem no banco de dados.
    """
    db_message = models.Message(
        patient_id=patient_id,
        text=text,
        has_alert=has_alert,
        sender=sender
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


# ### NOVAS FUNÇÕES CRUD PARA O PROFISSIONAL ###
def get_professional_by_email(db: Session, email: str):
    return db.query(models.Professional).filter(models.Professional.email == email).first()

def create_professional(db: Session, email: str, hashed_password: str):
    db_professional = models.Professional(email=email, hashed_password=hashed_password)
    db.add(db_professional)
    db.commit()
    db.refresh(db_professional)
    return db_professional
# ###########################################