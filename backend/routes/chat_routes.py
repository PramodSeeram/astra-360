import logging
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from database import SessionLocal, get_db
from sqlalchemy.orm import Session
from fastapi import Depends, APIRouter, HTTPException
from models import get_user_by_external_id, ChatMessage, ChatThread
from services.chat_service import build_chat_response
from services.chat_policy import ACTIVATION_REQUIRED_RESPONSE
from services.user_state import get_user_state
from services.agent_router import route_query
from services.decision_engine import run_decision_engine
from services.card_explainer import explain_decision

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Agent Chat"])


def _compound_card_and_finance_query(message: str) -> bool:
    """
    When the user combines a card/credit question with spending, budget, or savings
    in the same utterance, do not short-circuit into the deterministic card engine —
    the multi-agent graph should handle both intents.
    """
    m = (message or "").lower()
    if not any(sep in m for sep in (" and ", " & ", ";")):
        return False
    cardish = any(
        k in m
        for k in (
            "card",
            "credit card",
            "which card",
            "best card",
            "cibil",
            "credit score",
        )
    )
    finance_other = any(
        k in m
        for k in (
            "spend",
            "spent",
            "spending",
            "expense",
            "expenses",
            "how much",
            "budget",
            "save",
            "saving",
            "savings",
            "income",
            "analyze my",
        )
    )
    return cardish and finance_other

class ChatRequest(BaseModel):
    user_id: str
    message: str
    thread_id: Optional[int] = None
    agent_hint: Optional[str] = None


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


# ---------------------------------------------------------------------------
# Hybrid decision + LLM explanation handler
# ---------------------------------------------------------------------------

def _handle_card_recommendation(
    message: str,
    thread_id: int,
    thread_title: str,
) -> Optional[ChatResponse]:
    """
    Run the deterministic decision engine first.
    If a rule fires, call the LLM for explanation only and return immediately.
    Returns None when no rule matches so the normal pipeline continues.
    """
    decision = run_decision_engine(message)
    if decision is None:
        return None

    # LLM expands the reasoning — it cannot override the card choice
    explanation = explain_decision(decision, message)

    logger.info(
        "card_recommendation.decision card=%s rule=%s",
        decision.card,
        decision.matched_rule,
    )

    return ChatResponse(
        type="card_recommendation",
        response=(
            f"**Recommended Card:** {decision.card}\n\n"
            f"**Why:** {explanation}"
        ),
        actions=[],
        sources=["rule_engine"],
        confidence=1.0,
        data={
            "answer": decision.card,
            "reason": explanation,
            "matched_rule": decision.matched_rule,
            "decision_source": "rule_engine",
            "thread_id": thread_id,
            "thread_title": thread_title,
        },
    )

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

        # 1.5 — Hybrid Decision Engine: deterministic card recommendation.
        # This intercepts the request BEFORE the LLM pipeline so the LLM
        # never makes the card choice — it only expands the explanation.
        card_response = None
        if not _compound_card_and_finance_query(request.message):
            card_response = _handle_card_recommendation(
                request.message, thread.id, thread.title
            )
        if card_response is not None:
            # Persist both sides of the conversation
            db.add(ChatMessage(thread_id=thread.id, role="user", content=request.message))
            db.add(ChatMessage(thread_id=thread.id, role="assistant", content=card_response.response))
            db.commit()
            return card_response

        # 1.6 Detect route ONCE. Downstream services must never re-route.
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

        thread_id_for_save = thread.id
        thread_title_snapshot = thread.title or ""

        # 4. Dispatch to chat service with the precomputed route.
        result = build_chat_response(
            db=db,
            user=user,
            message=request.message,
            memory=memory,
            route=route,
            agent_hint=request.agent_hint,
        )

        # 5. Save assistant message on a fresh DB session. Long LLM work above can leave the
        # request-scoped MySQL connection idle past server timeout; pymysql then raises
        # InterfaceError on the next write if we reuse the same connection.
        try:
            db.rollback()
        except Exception:
            pass
        try:
            db.connection().invalidate()
        except Exception:
            pass

        with SessionLocal() as write_db:
            write_db.add(
                ChatMessage(
                    thread_id=thread_id_for_save,
                    role="assistant",
                    content=result["response"],
                )
            )
            write_db.commit()
            refreshed = write_db.get(ChatThread, thread_id_for_save)
            if refreshed and refreshed.title:
                thread_title_snapshot = refreshed.title

        merged_data = {
            **(result.get("data") or {}),
            "thread_id": thread_id_for_save,
            "thread_title": thread_title_snapshot,
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
