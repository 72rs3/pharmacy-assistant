from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app import models
from app.auth.utils import ALGORITHM, SECRET_KEY
from app.deps import get_current_pharmacy
from app.db import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


def require_owner(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.is_admin or current_user.pharmacy_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pharmacy owner privileges required",
        )
    return current_user


def require_approved_owner(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if current_user.is_admin:
        return current_user
    if current_user.pharmacy_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pharmacy owner privileges required",
        )

    pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == current_user.pharmacy_id).first()
    if pharmacy is None or not pharmacy.is_active or pharmacy.status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pharmacy is not approved yet",
        )
    return current_user


def require_pharmacy_owner(
    pharmacy: models.Pharmacy = Depends(get_current_pharmacy),
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if current_user.is_admin:
        return current_user
    if not pharmacy.is_active or pharmacy.status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pharmacy is not approved yet",
        )
    if current_user.pharmacy_id != pharmacy.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pharmacy owner privileges required",
        )
    return current_user
