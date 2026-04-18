from pathlib import Path

from services.knowledge_base_service import ingest_knowledge_documents


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[2]
    result = ingest_knowledge_documents(str(base_dir))
    print(result)
