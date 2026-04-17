import sys
import os
import json
import logging

# Add current directory to path
sys.path.append(os.getcwd())

from database import SessionLocal
from models import get_user_by_external_id
from services.context_builder import build_user_context
from agents.wealth_agent import detect_intent, get_chat_response

# Basic logging config
logging.basicConfig(level=logging.INFO)

def test_context_builder():
    print("\n--- Testing Context Builder ---")
    db = SessionLocal()
    user = get_user_by_external_id(db, "user_001")
    if user:
        context = build_user_context(db, user)
        print(f"User: {user.name}")
        print(json.dumps(context, indent=2))
    else:
        print("User user_001 NOT FOUND in database.")
    db.close()

def test_intent_detection():
    print("\n--- Testing Intent Detection ---")
    queries = [
        "What is my current budget?",
        "How much did I spend at Starbucks last month?",
        "I had a bike accident, what should I do?",
        "Hello assistant",
        "Give me a savings plan"
    ]
    for q in queries:
        intent, conf = detect_intent(q)
        print(f"Query: {q} \n-> Intent: {intent} (Conf: {conf})")

def test_chat_response():
    print("\n--- Testing Chat Response ---")
    db = SessionLocal()
    user = get_user_by_external_id(db, "user_001")
    if user:
        context = build_user_context(db, user)
        # Test a budget query
        query = "How can I save more money given my current EMIs?"
        intent, conf = detect_intent(query)
        result = get_chat_response(query, user_context=context, intent=intent)
        print(f"Query: {query}")
        print(f"Intent: {intent}")
        print(f"AI Response Snippet: {result['response'][:100]}...")
        print(f"UI Action: {result['ui_action']}")
        print(f"Actions: {result['actions']}")
    db.close()

if __name__ == "__main__":
    test_context_builder()
    test_intent_detection()
    test_chat_response()
