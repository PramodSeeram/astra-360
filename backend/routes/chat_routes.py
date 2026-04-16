import logging
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from agents.wealth_agent import get_chat_response, detect_intent
from database import get_db
from sqlalchemy.orm import Session
from fastapi import Depends, APIRouter, HTTPException
from models import get_user_by_external_id, get_or_create_thread, ChatMessage
from services.context_builder import build_user_context
from services.user_state import get_user_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Agent Chat"])

class ChatRequest(BaseModel):
    user_id: str
    message: str

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
        
        thread = get_or_create_thread(db, user)

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
        intent, confidence = detect_intent(request.message)
        logger.info(f"Detected intent: {intent} ({confidence})")

        # 3. Insurance Trigger
        # If user mentions accident/crash or intent is insurance, trigger upload flow
        insurance_keywords = ["accident", "crash", "damage", "hit", "insurance", "claim"]
        if intent == "insurance" or any(kw in request.message.lower() for kw in insurance_keywords):
            resp = ChatResponse(
                type="insurance_upload_required",
                response="I'm sorry to hear that. Please upload an image of the damage or document so I can analyze your insurance coverage.",
                ui_action="open_camera",
                actions=["upload_photo", "call_emergency"]
            )
            # Save message
            assistant_msg = ChatMessage(thread_id=thread.id, role="assistant", content=resp.response)
            db.add(assistant_msg)
            db.commit()
            return resp

        # 4. Build User Context
        user_context = build_user_context(db, user)

        # 5. Save User Message
        user_msg = ChatMessage(thread_id=thread.id, role="user", content=request.message)
        db.add(user_msg)
        db.commit()

        # 6. Get AI Response with Context
        result = get_chat_response(request.message, user_context=user_context, intent=intent)
        
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
            data=user_context if intent != "general" else None
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Chat Error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
