from typing import List, Optional

from pydantic import BaseModel


class TableData(BaseModel):
    title: str = ""
    headers: List[str]
    rows: List[List[str]]


class ExtractionResult(BaseModel):
    tables: List[TableData]
    raw_text_summary: Optional[str] = ""
