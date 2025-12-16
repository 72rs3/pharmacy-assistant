from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app import crud, models, schemas as app_schemas
from app.auth.deps import get_current_user
from app.auth import schemas, utils

router = APIRouter()


def _create_user(user_in: schemas.UserCreate, db: Session) -> models.User:
    existing = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    pharmacy = None
    if user_in.pharmacy_name:
        existing_pharmacy = (
            db.query(models.Pharmacy).filter(models.Pharmacy.name == user_in.pharmacy_name).first()
        )
        if existing_pharmacy:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pharmacy name already registered",
            )
        pharmacy = crud.create_pharmacy(
            db=db,
            pharmacy=app_schemas.PharmacyCreate(name=user_in.pharmacy_name),
        )

    hashed_pw = utils.hash_password(user_in.password)
    user = models.User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hashed_pw,
        is_admin=False,
        pharmacy_id=pharmacy.id if pharmacy else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/register-owner", response_model=schemas.UserOut)
def register_owner(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    return _create_user(user_in, db)


@router.post("/register", response_model=schemas.UserOut)
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    return _create_user(user_in, db)


@router.post("/login", response_model=schemas.Token)
def login(user_in: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if not user or not utils.verify_password(user_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = utils.create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=60 * 24),
    )

    return schemas.Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user
