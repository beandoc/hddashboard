from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, Text, ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from datetime import datetime

from db.engine import Base


class PatientMealRecord(Base):
    __tablename__ = "patient_meal_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    date = Column(Date, default=lambda: datetime.utcnow().date())
    calories = Column(Float)
    protein = Column(Float)
    phosphorus = Column(Float, nullable=True)
    potassium = Column(Float, nullable=True)
    calcium = Column(Float, nullable=True)
    meal_type = Column(String)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_patient_meal_records_patient_date', 'patient_id', 'date'),
    )

    patient = relationship("Patient", back_populates="meal_records")


class FoodDatabaseItem(Base):
    __tablename__ = "food_database_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    synonyms = Column(Text, nullable=True)
    serving_size = Column(String, nullable=True)
    serving_sizes = Column(Text, nullable=True)
    calories = Column(Float, nullable=False)
    protein = Column(Float, nullable=False)
    phosphorus = Column(Float, nullable=False)
    potassium = Column(Float, nullable=True)
    calcium = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
