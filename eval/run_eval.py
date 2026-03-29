import json

from app.core.config import get_settings
from app.services.factcheck_runner import run_factcheck


def main():
    settings = get_settings()

    with open("eval/dataset.jsonl", "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    for i, row in enumerate(rows, start=1):
        result = run_factcheck(
            input_text=row["input_text"],
            settings=settings,
            session_id=row.get("session_id"),
            search_budget=row.get("search_budget"),
            max_rounds_per_claim=row.get("max_rounds_per_claim"),
            enable_fetch=row.get("enable_fetch"),
            fetch_budget=row.get("fetch_budget"),
            max_claims=row.get("max_claims"),
            request_payload=row,
            persist=False,
            tags=["factcheck-ma", "eval"],
        )
        print(f"\n=== Case {i} ===")
        print(result.final_markdown[:1200])


if __name__ == "__main__":
    main()
