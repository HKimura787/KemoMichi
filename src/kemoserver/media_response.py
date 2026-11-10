"""Hold cache entries between generation and the end of HTTP file/range streaming."""

from pathlib import Path
from typing import Callable

from fastapi import HTTPException
from starlette.responses import FileResponse, Response

from kemocore.media import CacheLease


class _CachedFileResponse(FileResponse):
    def __init__(self, path: Path, lease: CacheLease, **kwargs):
        super().__init__(path, **kwargs)
        self.lease = lease

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.lease.close()


def cached_file_response(create: Callable[[], Path | None], *, media_type: str,
                         headers: dict[str, str], missing_status: int = 204) -> Response:
    lease = CacheLease()
    try:
        path = lease.generate(create)
        if path is None:
            lease.close()
            if missing_status == 204:
                return Response(status_code=204)
            raise HTTPException(missing_status, detail={"error": "error.videoUnplayable"})
        return _CachedFileResponse(path, lease, media_type=media_type, headers=headers)
    except BaseException:
        lease.close()
        raise
