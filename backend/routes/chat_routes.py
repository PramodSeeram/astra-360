import logging
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from agents.wealth_agent import get_chat_response, detect_agent, detect_intent
from database import get_db
from sqlalchemy.orm import Session
from fastapi import Depends, APIRouter, HTTPException
from models import get_user_by_external_id, ChatMessage, ChatThread
from services.context_builder import build_user_context
from services.user_state import get_user_state

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

        # 1.5 Check User State for Activation Prompt
        state = get_user_state(db, user)
        if state == "PARTIAL" and any(kw in request.message.lower() for kw in ["how", "help", "show", "get", "start"]):
             return ChatResponse(
                type="activation_required",
                response="To provide personalized insights, I need to analyze your financial data. Please upload your bank statement.",
                ui_action="open_file_upload",
                actions=["upload_now", "how_it_works"]
            )

        # 2. Detect Intent
        routed_agent = detect_agent(request.message)
        intent_data = {
            "agent": routed_agent,
            "intent": detect_intent(request.message),
        }
        if isinstance(intent_data, dict):
            intent = intent_data.get("agent", "wealth")
            confidence = intent_data.get("confidence", 1.0)
        else:
            intent = intent_data
            confidence = 1.0
        logger.info(f"Detected agent: {intent} ({confidence})")

        # 3. Build User Context
        user_context = build_user_context(db, user)

        # 4. Save User Message
        user_msg = ChatMessage(thread_id=thread.id, role="user", content=request.message)
        db.add(user_msg)
        if not thread.title or thread.title == "Main Chat":
            thread.title = _build_thread_title(request.message)
        db.commit()

        # 5. Build compact conversation memory after saving the latest user answer.
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

        # 6. Get AI Response with context and memory.
        result = get_chat_response(
            request.message,
            user_context=user_context,
            intent_data=intent_data,
            memory=memory,
        )

        # 7. Save Assistant Message
        assistant_msg = ChatMessage(thread_id=thread.id, role="assistant", content=result["response"])
        db.add(assistant_msg)
        db.commit()

        return ChatResponse(
            type=result.get("type", "general"),
            response=result["response"],
            ui_action=result.get("ui_action"),
            actions=result.get("actions", []),
            sources=result["sources"],
            confidence=confidence,
            data={
                **(user_context if intent == "wealth" else {}),
                "thread_id": thread.id,
                "thread_title": thread.title,
            } if intent == "wealth" else {"thread_id": thread.id, "thread_title": thread.title}
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
