"""Database and business logic for scans. Routers call this; it never imports FastAPI.

STUB(E8): nothing is saved. A real signed QR token (from registration, E4) or a
fake runner's bib (e.g. H0004) is accepted; anything else is `invalid`.
"""

from app.core.errors import AppError
from app.core.security import parse_qr_token
from app.modules.scans.schemas import ScanBatchIn, ScanBatchOut, ScanResult
from app.stubs import race


def _bib_for_token(token: str) -> str | None:
    try:
        return parse_qr_token(token)[1]
    except AppError:
        pass
    r = race.runner_by_bib(token)
    return r.bib_number if r else None


async def ingest_batch(body: ScanBatchIn) -> ScanBatchOut:
    results = []
    seen: set[str] = set()
    for scan in body.scans:
        bib = _bib_for_token(scan.qr_token)
        if bib is None:
            status = "invalid"
        elif bib in seen:
            status = "duplicate"
        else:
            status = "accepted"
            seen.add(bib)
        results.append(ScanResult(client_id=scan.client_id, status=status, bib_number=bib))  # type: ignore[arg-type]
    return ScanBatchOut(results=results)
