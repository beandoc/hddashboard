from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from db.engine import Base


class ResearchProject(Base):
    __tablename__ = "research_projects"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    status = Column(String, default="Active")
    created_at = Column(DateTime, default=datetime.utcnow)

    records = relationship("ResearchRecord", back_populates="project", cascade="all, delete-orphan")


class ResearchRecord(Base):
    __tablename__ = "research_records"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("research_projects.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)

    test_type = Column(String, nullable=False)
    test_date = Column(Date, default=lambda: datetime.utcnow().date())
    data = Column(Text)
    notes = Column(Text)
    entered_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("ResearchProject", back_populates="records")
    patient = relationship("Patient", back_populates="research_records")
