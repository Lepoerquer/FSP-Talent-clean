from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List

try:
    from backend.app.core.database import get_db
    from backend.app.models.chat import ChatMessageModel
    from backend.app.modules.auth.service import get_current_user
    from backend.app.models.user import User
except ImportError:
    from app.core.database import get_db
    from app.models.chat import ChatMessageModel
    from app.modules.auth.service import get_current_user
    from app.models.user import User

router = APIRouter(prefix="/chat", tags=["Chat"])

class ChatMessage(BaseModel):
    id: str
    sender_id: str
    receiver_id: str = ""
    message: str
    created_at: str

    model_config = {"from_attributes": True}

class ChatMessageCreate(BaseModel):
    message: str
    receiver_id: str

@router.post("/messages", response_model=ChatMessage)
def send_message(
    payload: ChatMessageCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Отправка сообщения во внутреннем чате (Bonus)."""
    msg = ChatMessageModel(
        sender_id=current_user.id,
        receiver_id=payload.receiver_id,
        message=payload.message
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    
    return ChatMessage(
        id=msg.id,
        sender_id=msg.sender_id,
        receiver_id=msg.receiver_id,
        message=msg.message,
        created_at=msg.created_at.isoformat()
    )


@router.get("/messages", response_model=List[ChatMessage])
def get_messages(
    receiver_id: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Возвращает историю сообщений (с опциональной фильтрацией по контрагенту диалога)."""
    try:
        from backend.app.models.candidate import CandidateProfile
        from backend.app.models.company import EmployerMember
    except ImportError:
        from app.models.candidate import CandidateProfile
        from app.models.company import EmployerMember

    cand = db.query(CandidateProfile).filter(CandidateProfile.user_id == current_user.id).first()
    emp = db.query(EmployerMember).filter(EmployerMember.user_id == current_user.id).first()

    aliases = [current_user.id]
    if cand:
        aliases.append(cand.id)
    if emp:
        aliases.append(emp.company_id)

    query = db.query(ChatMessageModel).filter(
        (ChatMessageModel.sender_id.in_(aliases)) | 
        (ChatMessageModel.receiver_id.in_(aliases))
    )

    if receiver_id:
        target_aliases = [receiver_id]
        target_cand = db.query(CandidateProfile).filter((CandidateProfile.id == receiver_id) | (CandidateProfile.user_id == receiver_id)).first()
        if target_cand:
            target_aliases.extend([target_cand.id, target_cand.user_id])
        target_members = db.query(EmployerMember).filter((EmployerMember.company_id == receiver_id) | (EmployerMember.user_id == receiver_id)).all()
        for m in target_members:
            target_aliases.extend([m.company_id, m.user_id])
        target_aliases = list(set(target_aliases))

        query = query.filter(
            ((ChatMessageModel.sender_id.in_(aliases)) & (ChatMessageModel.receiver_id.in_(target_aliases))) |
            ((ChatMessageModel.sender_id.in_(target_aliases)) & (ChatMessageModel.receiver_id.in_(aliases)))
        )

    msgs = query.order_by(ChatMessageModel.created_at.asc()).all()
    
    return [
        ChatMessage(
            id=m.id,
            sender_id=m.sender_id,
            receiver_id=m.receiver_id,
            message=m.message,
            created_at=m.created_at.isoformat()
        )
        for m in msgs
    ]
