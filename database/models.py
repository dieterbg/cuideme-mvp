from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    
    # ### NOVO CAMPO ###
    # Define o modo de operação para este paciente.
    # 'automatico' (padrão) ou 'manual'
    status = Column(String, default="automatico", nullable=False)
    
    messages = relationship("Message", back_populates="patient")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    text = Column(String, nullable=False)
    sender = Column(String, default="patient") # 'patient' ou 'system'
    has_alert = Column(Boolean, default=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    patient = relationship("Patient", back_populates="messages")
