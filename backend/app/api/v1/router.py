from fastapi import APIRouter

from app.api.v1 import (
    appointments,
    approvals,
    audit,
    auth,
    chat,
    copilot,
    doctors,
    doctors_profile,
    documents,
    exports,
    files,
    health,
    kg,
    lab_orders,
    medications,
    ml,
    notify,
    patients,
    queue,
    triage,
    users,
    visits,
    ws,
)

api_router = APIRouter()
api_router.include_router(health.router)

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth.router)
v1_router.include_router(users.router)
v1_router.include_router(patients.router)
v1_router.include_router(files.router)
v1_router.include_router(approvals.router)
v1_router.include_router(audit.router)
v1_router.include_router(notify.router)
v1_router.include_router(doctors_profile.router)
v1_router.include_router(exports.router)
v1_router.include_router(triage.router)
v1_router.include_router(chat.router)
v1_router.include_router(copilot.router)
v1_router.include_router(kg.router)
v1_router.include_router(visits.router)
v1_router.include_router(documents.router)
v1_router.include_router(ml.router)
v1_router.include_router(doctors.router)
v1_router.include_router(appointments.router)
v1_router.include_router(queue.router)
v1_router.include_router(lab_orders.router)
v1_router.include_router(medications.router)

api_router.include_router(v1_router)
api_router.include_router(ws.router)
