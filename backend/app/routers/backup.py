from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import BackupImportRequest, BackupImportResponse
from app.services.backup import export_backup, import_backup

router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.get("/export")
def backup_export(db: Session = Depends(get_db)):
    data = export_backup(db)
    filename = f"comic-lists-backup-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", response_model=BackupImportResponse)
def backup_import(payload: BackupImportRequest, db: Session = Depends(get_db)):
    try:
        result = import_backup(db, payload.data, replace=payload.replace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BackupImportResponse(**result)
