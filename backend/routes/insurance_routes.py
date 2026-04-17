import logging
import os
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import get_user_by_external_id
from agents.wealth_agent import client, LLM_MODEL
from services.context_builder import build_user_context
import json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/insurance", tags=["Insurance"])

@router.post("/analyze")
async def analyze_insurance_image(
    user_id: str = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Analyzes an insurance-related image (e.g., accident photo, policy doc).
    Uses a placeholder for OCR and LLM for analysis.
    """
    try:
        # 1. Fetch User and Context
        user = get_user_by_external_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        
        context = build_user_context(db, user)
        
        # 2. Mock OCR / Image Analysis
        # In a real app, we might use a Vision model or pytesseract here.
        # For the demo, we simulate OCR extraction based on the filename or just a generic placeholder.
        image_text = f"Sample insurance document extraction from {image.filename}. "
        if "accident" in image.filename.lower() or "crash" in image.filename.lower():
            image_text += "Detected vehicle damage, broken headlight, front bumper impact."
        else:
            image_text += "Detected policy document, coverage for comprehensive car insurance."

        # 3. Call LLM for final Analysis
        prompt = f"""
        USER INSURANCE CONTEXT:
        {json.dumps(context.get('loans', []), indent=2)}
        {json.dumps(context.get('profile', []), indent=2)}

        IMAGE ANALYSIS (OCR):
        {image_text}

        TASK:
        - Identify damage type or document intent.
        - Estimate coverage relevance.
        - Suggest next steps.

        Return ONLY JSON:
        {{
            "type": "insurance_analysis",
            "damage_type": "car accident",
            "coverage": "partial / full / unknown",
            "recommendation": "string",
            "next_steps": ["step1", "step2"]
        }}
        """

        completion = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        
        analysis_result = completion.choices[0].message.content
        start = analysis_result.find('{')
        end = analysis_result.rfind('}') + 1
        if start != -1 and end != -1:
            return json.loads(analysis_result[start:end])
        
        return {
            "type": "insurance_analysis",
            "damage_type": "General Inquiry",
            "coverage": "Check Policy",
            "recommendation": "Please contact your agent.",
            "next_steps": ["Review policy documents"]
        }

    except Exception as e:
        logger.error(f"Insurance Analysis Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
