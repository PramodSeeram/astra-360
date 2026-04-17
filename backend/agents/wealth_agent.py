import os
import logging
import json
from typing import Dict, Any, List
from openai import OpenAI
from rag.embeddings import generate_single_embedding
from rag.vector_store import search_documents

logger = logging.getLogger(__name__)

# Configure LLM Client (RunPod GPU - Ollama)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://0ruool8gerdycr-11434.proxy.runpod.net")
if not LLM_BASE_URL.endswith("/v1"):
    OLLAMA_BASE_URL = f"{LLM_BASE_URL}/v1"
else:
    OLLAMA_BASE_URL = LLM_BASE_URL

LLM_MODEL = os.getenv("LLM_MODEL", "mistral")

# Initialize client
client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key="runpod",
)

def detect_intent(query: str) -> str:
    """Classifies user query into budget, finance, insurance, or general."""
    prompt = f"""
    Classify the following user query into ONE of these categories:
    - budget: Queries about planning, saving, limits, or financial goals.
    - finance: Queries about bank accounts, credit cards, loans, or specific transactions.
    - insurance: Queries about accidents, claims, policies, or coverage.
    - upload: Queries about uploading bank statements, files, or activating data.
    - general: Anything else.

    User Query: "{query}"

    Return ONLY JSON:
    {{"intent": "category_name", "confidence": 0.0-1.0}}
    """
    
    try:
        completion = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        content = completion.choices[0].message.content
        # Basic JSON extraction
        start = content.find('{')
        end = content.rfind('}') + 1
        if start != -1 and end != -1:
            data = json.loads(content[start:end])
            return data.get("intent", "general"), data.get("confidence", 0.5)
        return "general", 0.5
    except Exception as e:
        logger.error(f"Error detecting intent: {e}")
        return "general", 0.0

def get_chat_response(query: str, user_context: Dict[str, Any] = None, intent: str = "general") -> Dict[str, Any]:
    """Processes a user query by doing RAG and passing user financial context to an LLM."""
    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    # 1. RAG (Optional depending on intent, but let's keep it for finance/budget)
    context_chunks = ""
    sources = []
    if intent in ["finance", "budget", "general"]:
        try:
            query_embedding = generate_single_embedding(query)
            results = search_documents(query_embedding, top_k=3)
            if results:
                context_chunks = "\n\n".join([res.get("text", "") for res in results])
                sources = list(set([res.get("metadata", {}).get("filename", "unknown") for res in results if res.get("metadata", {}).get("filename")]))
        except Exception as e:
            logger.error(f"RAG Error: {e}")

    # 2. Build Structured Prompt
    context_str = json.dumps(user_context, indent=2) if user_context else "No specific user data available."
    
    prompt = f"""
    You are a premium financial AI assistant named Astra.
    
    USER FINANCIAL CONTEXT:
    {context_str}

    RAG CONTEXT (from uploaded files):
    {context_chunks}

    INTENT: {intent}
    
    INSTRUCTIONS:
    - Answer the question based on the user's financial context and provided files.
    - Be practical, personalized, and proactive.
    - If user asks about budget, provide a structured plan.
    - If user asks about spending, analyze their transactions.
    - If the answer is not in context, use general financial wisdom but mention it.
    
    USER QUESTION: "{query}"
    
    Return your response in structure:
    RESPONSE: [Your natural language response]
    FOLLOW_UP: [List of 2-3 short action tags, e.g., "reduce_dining", "view_cards"]
    """

    try:
        completion = client.chat.completions.create(
            model=LLM_MODEL, 
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        raw_output = completion.choices[0].message.content
        
        # Simple parsing for RESPONSE and FOLLOW_UP
        parts = raw_output.split("FOLLOW_UP:")
        response_text = parts[0].replace("RESPONSE:", "").strip()
        follow_ups = []
        if len(parts) > 1:
            # Extract tags like "tag1", "tag2"
            follow_ups = [tag.strip().strip('"') for tag in parts[1].split(",") if tag.strip()]

        # Determine UI Action
        ui_action = None
        if intent == "budget":
            ui_action = "show_budget_chart"
        elif intent == "finance" and "card" in query.lower():
            ui_action = "view_cards"
        elif intent == "upload" or any(kw in query.lower() for kw in ["upload", "statement", "bank data"]):
            ui_action = "open_file_upload"

        return {
            "type": "upload_required" if intent == "upload" or ui_action == "open_file_upload" else (intent if intent != "general" else "financial_insight"),
            "response": response_text,
            "ui_action": ui_action,
            "actions": follow_ups[:3],
            "sources": sources
        }
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        raise RuntimeError("Failed to generate response from the LLM.")
