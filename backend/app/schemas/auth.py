from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    username: str
    role: str


class MeResponse(BaseModel):
    id: int
    username: str
    role: str
