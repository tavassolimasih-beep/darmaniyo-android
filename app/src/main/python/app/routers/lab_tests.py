import os
import uuid
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.security import get_current_user
from app.templating import templates

router = APIRouter(prefix="/lab-tests", tags=["lab_tests"])

UPLOAD_DIR = os.path.join("static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.get("")
def list_lab_tests(
    request: Request,
    status: Optional[str] = None,
    workflow: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = db.query(models.LabTest)
    if status in models.LabTestStatus.__members__:
        query = query.filter(models.LabTest.status == models.LabTestStatus[status])
    if workflow in models.TestWorkflowStatus.__members__:
        query = query.filter(models.LabTest.workflow_status == models.TestWorkflowStatus[workflow])
    tests = query.order_by(models.LabTest.ordered_at.desc()).all()
    return templates.TemplateResponse(
        "lab_tests.html", {"request": request, "user": user, "tests": tests, "status_filter": status, "workflow_filter": workflow}
    )


@router.get("/new")
def new_lab_test_form(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    patient_id: Optional[int] = None,
):
    patients = db.query(models.Patient).order_by(models.Patient.full_name).all()
    return templates.TemplateResponse(
        "lab_test_form.html",
        {"request": request, "user": user, "patients": patients, "test": None, "preselect_patient_id": patient_id},
    )


@router.post("/new")
def create_lab_test(
    patient_id: int = Form(...),
    test_name: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    test = models.LabTest(patient_id=patient_id, test_name=test_name, status=models.LabTestStatus.pending)
    db.add(test)
    db.commit()
    return RedirectResponse("/lab-tests", status_code=303)


@router.get("/{test_id}/edit")
def edit_lab_test_form(
    test_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    test = db.query(models.LabTest).filter(models.LabTest.id == test_id).first()
    if not test:
        return RedirectResponse("/lab-tests", status_code=303)
    patients = db.query(models.Patient).order_by(models.Patient.full_name).all()
    return templates.TemplateResponse(
        "lab_test_form.html", {"request": request, "user": user, "patients": patients, "test": test, "preselect_patient_id": test.patient_id}
    )


@router.post("/{test_id}/edit")
def update_lab_test(
    test_id: int,
    patient_id: int = Form(...),
    test_name: str = Form(...),
    result_text: Optional[str] = Form(None),
    mark_done: Optional[str] = Form(None),
    result_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    test = db.query(models.LabTest).filter(models.LabTest.id == test_id).first()
    if not test:
        return RedirectResponse("/lab-tests", status_code=303)

    test.patient_id = patient_id
    test.test_name = test_name
    test.result_text = result_text

    if result_file and result_file.filename:
        ext = os.path.splitext(result_file.filename)[1]
        safe_name = f"{uuid.uuid4().hex}{ext}"
        dest_path = os.path.join(UPLOAD_DIR, safe_name)
        with open(dest_path, "wb") as f:
            f.write(result_file.file.read())
        test.result_file = f"/static/uploads/{safe_name}"

    if mark_done:
        test.status = models.LabTestStatus.done
        test.workflow_status = models.TestWorkflowStatus.done

    db.commit()
    return RedirectResponse("/lab-tests", status_code=303)


@router.post("/{test_id}/delete")
def delete_lab_test(
    test_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    test = db.query(models.LabTest).filter(models.LabTest.id == test_id).first()
    if test:
        db.delete(test)
        db.commit()
    return RedirectResponse("/lab-tests", status_code=303)
