from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredObject:
    object_id: str
    content_type: str
    size_bytes: int
    checksum_sha256: str


class ObjectStorage(Protocol):
    async def put(
        self,
        *,
        owner_id: str,
        object_id: str,
        content: bytes,
        content_type: str,
    ) -> StoredObject: ...

    async def create_download_url(
        self,
        *,
        owner_id: str,
        object_id: str,
        expires_in: timedelta,
    ) -> str: ...

    async def delete(self, *, owner_id: str, object_id: str) -> None: ...
