from fastapi import APIRouter

try:
    from backend.app.modules.assessment.router import grade_router
    from backend.app.modules.assessment.router import router as assessment_router
    from backend.app.modules.auth.router import router as auth_router
    from backend.app.modules.consents.router import router as consents_router
    from backend.app.modules.dictionaries.router import router as dictionaries_router
    from backend.app.modules.fsp.router import router as fsp_router
    from backend.app.modules.invitations.router import router as invitations_router
    from backend.app.modules.matching.router import router as matching_router
    from backend.app.modules.profiles.router import router as profiles_router
    from backend.app.modules.ats.router import router as ats_router
    from backend.app.modules.chat.router import router as chat_router
except ImportError:
    from app.modules.assessment.router import grade_router
    from app.modules.assessment.router import router as assessment_router
    from app.modules.auth.router import router as auth_router
    from app.modules.consents.router import router as consents_router
    from app.modules.dictionaries.router import router as dictionaries_router
    from app.modules.fsp.router import router as fsp_router
    from app.modules.invitations.router import router as invitations_router
    from app.modules.matching.router import router as matching_router
    from app.modules.profiles.router import router as profiles_router
    from app.modules.ats.router import router as ats_router
    from app.modules.chat.router import router as chat_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(consents_router)
api_router.include_router(dictionaries_router)
api_router.include_router(assessment_router)
api_router.include_router(grade_router)
api_router.include_router(invitations_router)
api_router.include_router(matching_router)
api_router.include_router(fsp_router)
api_router.include_router(profiles_router)
api_router.include_router(ats_router)
api_router.include_router(chat_router)
