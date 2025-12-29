from fastapi import Header, HTTPException, status


def get_current_pharmacy_id(pharmacy_id: int | None = Header(None, alias="X-Pharmacy-ID")) -> int:
    if pharmacy_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Pharmacy-ID header required",
        )
    return pharmacy_id
