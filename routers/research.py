from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date as date_type, datetime
import json

from database import get_db, Patient, ResearchProject, ResearchRecord, MonthlyRecord, SessionRecord
from config import templates
from dependencies import get_user, _require_admin_role

router = APIRouter(prefix="/research", tags=["research"])

@router.get("", response_class=HTMLResponse)
async def research_hub(request: Request, db: Session = Depends(get_db)):
    _require_admin_role(request) # Only admins/doctors
    projects = db.query(ResearchProject).order_by(ResearchProject.created_at.desc()).all()
    return templates.TemplateResponse("research_hub.html", {
        "request": request,
        "projects": projects,
        "user": get_user(request)
    })

@router.post("/projects")
async def create_project(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db)
):
    _require_admin_role(request)
    project = ResearchProject(title=title, description=description)
    db.add(project)
    db.commit()
    return RedirectResponse(url="/research", status_code=303)

@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def view_project(project_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin_role(request)
    project = db.query(ResearchProject).filter(ResearchProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404)
        
    records = db.query(ResearchRecord).filter(ResearchRecord.project_id == project_id).order_by(ResearchRecord.test_date.desc()).all()
    patients = db.query(Patient).filter(Patient.is_active == True).all()
    
    # Parse JSON data for display
    parsed_records = []
    for r in records:
        try:
            parsed_data = json.loads(r.data) if r.data else {}
        except:
            parsed_data = {}
        parsed_records.append({"record": r, "parsed_data": parsed_data, "patient": r.patient})
        
    return templates.TemplateResponse("research_project.html", {
        "request": request,
        "project": project,
        "records": parsed_records,
        "patients": patients,
        "user": get_user(request)
    })

@router.get("/projects/{project_id}/record", response_class=HTMLResponse)
async def new_record_form(project_id: int, patient_id: int, test_type: str, request: Request, db: Session = Depends(get_db)):
    project = db.query(ResearchProject).filter(ResearchProject.id == project_id).first()
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not project or not patient:
        raise HTTPException(status_code=404)
        
    from dynamic_vars import get_all_variables
    all_variables = get_all_variables(db)

    # Fetch latest clinical data for auto-filling
    latest_monthly = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.desc()).first()
    latest_session = db.query(SessionRecord).filter(SessionRecord.patient_id == patient_id).order_by(SessionRecord.session_date.desc()).first()

    dialysis_years = None
    if patient.hd_wef_date:
        from datetime import date as date_obj
        delta = date_obj.today() - patient.hd_wef_date
        dialysis_years = round(delta.days / 365.25, 1)
        
    return templates.TemplateResponse("research_record_form.html", {
        "request": request,
        "project": project,
        "patient": patient,
        "test_type": test_type,
        "all_variables": all_variables,
        "latest_monthly": latest_monthly,
        "latest_session": latest_session,
        "dialysis_years": dialysis_years,
        "user": get_user(request)
    })

@router.post("/projects/{project_id}/record")
async def save_record(
    project_id: int,
    request: Request,
    patient_id: int = Form(...),
    test_type: str = Form(...),
    test_date: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db)
):
    _require_admin_role(request)
    user = get_user(request)
    
    form_data = await request.form()
    
    # Extract all test-specific fields (exclude standard fields)
    standard_fields = ["patient_id", "test_type", "test_date", "notes"]
    test_data = {}
    for key, value in form_data.items():
        if key not in standard_fields and value != "":
            test_data[key] = value
            
    try:
        parsed_date = datetime.strptime(test_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        parsed_date = date_type.today()

    record = ResearchRecord(
        project_id=project_id,
        patient_id=patient_id,
        test_type=test_type,
        test_date=parsed_date,
        data=json.dumps(test_data),
        notes=notes,
        entered_by=(user.get("username") if isinstance(user, dict) else user.username) if user else "Admin"
    )
    
    db.add(record)
    db.commit()
    return RedirectResponse(url=f"/research/projects/{project_id}", status_code=303)

@router.post("/projects/{project_id}/delete")
async def delete_project(project_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin_role(request)
    project = db.query(ResearchProject).filter(ResearchProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404)
    db.delete(project)
    db.commit()
    return RedirectResponse(url="/research", status_code=303)

@router.post("/projects/{project_id}/records/{record_id}/delete")
async def delete_record(project_id: int, record_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin_role(request)
    record = db.query(ResearchRecord).filter(ResearchRecord.id == record_id, ResearchRecord.project_id == project_id).first()
    if not record:
        raise HTTPException(status_code=404)
    db.delete(record)
    db.commit()
    return RedirectResponse(url=f"/research/projects/{project_id}", status_code=303)
