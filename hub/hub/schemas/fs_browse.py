from typing import List, Optional

from pydantic import BaseModel


class DirectoryEntryResponse(BaseModel):
    name: str
    path: str


class DirectoryListingResponse(BaseModel):
    path: str
    parent: Optional[str]
    entries: List[DirectoryEntryResponse]
    reason: Optional[str] = None


class RootsResponse(BaseModel):
    roots: List[DirectoryEntryResponse]
