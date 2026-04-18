import logging
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from database import get_db
from sqlalchemy.orm import Session
from fastapi import Depends, APIRouter, HTTPException
from models import get_user_by_external_id, ChatMessage, ChatThread
from services.chat_service import build_chat_response
from services.chat_policy import ACTIVATION_REQUIRED_RESPONSE
from services.user_state import get_user_state
from services.agent_router import route_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Agent Chat"])

class ChatRequest(BaseModel):
    user_id: str
    message: str
    thread_id: Optional[int] = None


class ChatThreadSummary(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str
    preview: Optional[str] = None


def _get_thread_for_request(db: Session, user_id: int, thread_id: Optional[int]) -> Optional[ChatThread]:
    if thread_id is None:
        return None
    return (
        db.query(ChatThread)
        .filter(ChatThread.id == thread_id, ChatThread.user_id == user_id)
        .first()
    )


def _build_thread_title(message: str) -> str:
    text = " ".join((message or "").strip().split())
    return (text[:40].rstrip() or "New Chat")

class ChatResponse(BaseModel):
    type: str
    response: str
    ui_action: Optional[str] = None
    actions: List[str] = []
    sources: List[str] = []
    confidence: Optional[float] = None
    data: Optional[Dict[str, Any]] = None

@router.post("", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db)):
    """
    Upgraded chat endpoint with intent routing, context awareness,
    and structured responses for UI actions.
    """
    try:
        if not request.message or not request.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty.")

        # 1. Fetch User and Thread
        user = get_user_by_external_id(db, request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        thread = _get_thread_for_request(db, user.id, request.thread_id)
        if request.thread_id is not None and not thread:
            raise HTTPException(status_code=404, detail="Thread not found.")
        if thread is None:
            thread = ChatThread(user_id=user.id, title=_build_thread_title(request.message))
            db.add(thread)
            db.commit()
            db.refresh(thread)

        # 1.5 Detect route ONCE. Downstream services must never re-route.
        route = route_query(request.message)

        # 1.6 Check User State for Activation Prompt — only block generic
        # requests; finance questions are answered from the latest DB snapshot
        # even in PARTIAL state.
        state = get_user_state(db, user)
        if (
            state == "PARTIAL"
            and route.agent != "finance_agent"
            and any(kw in request.message.lower() for kw in ["help", "show", "get", "start", "upload"])
        ):
            activation = ACTIVATION_REQUIRED_RESPONSE
            return ChatResponse(
                type=activation["type"],
                response=activation["response"],
                ui_action=activation.get("ui_action"),
                actions=activation.get("actions", []),
                sources=activation.get("sources", []),
                confidence=activation.get("confidence"),
                data={
                    **activation.get("data", {}),
                    "thread_id": thread.id,
                    "thread_title": thread.title,
                    "route": {
                        "agent": route.agent,
                        "category": route.category,
                        "reason": "activation_required",
                        "confidence": route.confidence,
                    },
                },
            )

        logger.info(
            "chat.route agent=%s category=%s reason=%s confidence=%.2f",
            route.agent, route.category, route.reason, route.confidence,
        )

        # 2. Save User Message
        user_msg = ChatMessage(thread_id=thread.id, role="user", content=request.message)
        db.add(user_msg)
        if not thread.title or thread.title == "Main Chat":
            thread.title = _build_thread_title(request.message)
        db.commit()

        # 3. Build compact conversation memory after saving the latest user answer.
        recent_messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.thread_id == thread.id)
            .order_by(ChatMessage.timestamp.desc(), ChatMessage.id.desc())
            .limit(5)
            .all()
        )
        memory = [
            {"role": msg.role, "content": msg.content}
            for msg in reversed(recent_messages)
        ]

        # 4. Dispatch to chat service with the precomputed route.
        result = build_chat_response(
            db=db,
            user=user,
            message=request.message,
            memory=memory,
            route=route,
        )

        # 5. Save Assistant Message
        assistant_msg = ChatMessage(thread_id=thread.id, role="assistant", content=result["response"])
        db.add(assistant_msg)
        db.commit()

        merged_data = {
            **(result.get("data") or {}),
            "thread_id": thread.id,
            "thread_title": thread.title,
            "route": {
                "agent": route.agent,
                "category": route.category,
                "reason": result.get("reason") or route.reason,
                "confidence": route.confidence,
                "keywords_matched": list(route.keywords_matched),
            },
        }

        return ChatResponse(
            type=result.get("type", route.agent),
            response=result["response"],
            ui_action=result.get("ui_action"),
            actions=result.get("actions", []),
            sources=result.get("sources", []),
            confidence=result.get("confidence"),
            data=merged_data,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Chat Error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads", response_model=List[ChatThreadSummary])
def get_threads(user_id: str, db: Session = Depends(get_db)):
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required.")

    user = get_user_by_external_id(db, user_id.strip())
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    threads = (
        db.query(ChatThread)
        .filter(ChatThread.user_id == user.id)
        .order_by(ChatThread.created_at.desc(), ChatThread.id.desc())
        .all()
    )

    results: List[ChatThreadSummary] = []
    for thread in threads:
        latest_message = (
            db.query(ChatMessage)
            .filter(ChatMessage.thread_id == thread.id)
            .order_by(ChatMessage.timestamp.desc(), ChatMessage.id.desc())
            .first()
        )
        updated_at = latest_message.timestamp if latest_message else thread.created_at
        preview = latest_message.content[:80] if latest_message else None
        results.append(
            ChatThreadSummary(
                id=thread.id,
                title=thread.title or "New Chat",
                created_at=thread.created_at.isoformat(),
                updated_at=updated_at.isoformat(),
                preview=preview,
            )
        )
    return results


@router.get("/history")
def get_history(user_id: str, thread_id: int, db: Session = Depends(get_db)):
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required.")

    user = get_user_by_external_id(db, user_id.strip())
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    thread = _get_thread_for_request(db, user.id, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")

    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id == thread.id)
        .order_by(ChatMessage.timestamp.asc(), ChatMessage.id.asc())
        .all()
    )
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "timestamp": m.timestamp.isoformat(),
            "thread_id": thread.id,
        }
        for m in msgs
    ]
