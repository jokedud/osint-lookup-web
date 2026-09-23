from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel


class Result(BaseModel):
    source: str
    category: Literal["email", "username", "phone"]
    site: str
    status: Literal["found", "not_found", "rate_limited", "error", "info"]
    url: Optional[str] = None
    details: Dict[str, Any] = {}
