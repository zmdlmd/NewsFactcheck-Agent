import json
import logging
from datetime import datetime, timezone

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def json_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
