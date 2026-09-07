from pydantic import BaseModel, EmailStr, ConfigDict, Field


class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = None


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=256)
    pharmacy_name: str | None = Field(default=None, max_length=120)  # owners can supply a new pharmacy name
    pharmacy_domain: str | None = Field(default=None, max_length=255)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


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
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class AdminPasswordResetIn(BaseModel):
    email: EmailStr
    new_password: str = Field(min_length=8, max_length=256)
