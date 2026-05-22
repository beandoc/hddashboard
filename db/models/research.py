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
    start_date = Column(Date, nullable=True)
    test_types = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # NO cascade delete — research records (patient data) must survive project deletion.
    records = relationship("ResearchRecord", back_populates="project", passive_deletes=True)


class ResearchRecord(Base):
    __tablename__ = "research_records"

    id = Column(Integer, primary_key=True, index=True)
    # nullable=True so records can be orphaned (project_id set to NULL) when a project is deleted
    # without losing the patient's recorded data.
    project_id = Column(Integer, ForeignKey("research_projects.id", ondelete="SET NULL"), nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)

    test_type = Column(String, nullable=False)
    test_date = Column(Date, default=lambda: datetime.utcnow().date())
    data = Column(Text)
    notes = Column(Text)
    entered_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("ResearchProject", back_populates="records")
    patient = relationship("Patient", back_populates="research_records")
