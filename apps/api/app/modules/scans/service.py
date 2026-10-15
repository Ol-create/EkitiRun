"""Database and business logic for scans. Routers call this; it never imports FastAPI.

STUB(E8): nothing is saved. A `qr_token` that is a fake runner's bib (e.g. H0004)
or `STUB:<runner_id>` is accepted; anything else is `invalid`.
"""

from app.modules.scans.schemas import ScanBatchIn, ScanBatchOut, ScanResult
from app.stubs import race


def _bib_for_token(token: str) -> str | None:
    if token.startswith("STUB:"):
        rid = token.removeprefix("STUB:")
        r = next((x for x in race.runners() if str(x.runner_id) == rid), None)
        return r.bib_number if r else None
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
