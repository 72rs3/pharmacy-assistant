from pydantic import BaseModel, EmailStr, ConfigDict


class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = None


class UserCreate(UserBase):
    password: str
    pharmacy_name: str | None = None  # owners can supply a new pharmacy name
    pharmacy_domain: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(UserBase):
    id: int
    is_admin: bool
    pharmacy_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: int | None = None


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


class AdminPasswordResetIn(BaseModel):
    email: EmailStr
    new_password: str
