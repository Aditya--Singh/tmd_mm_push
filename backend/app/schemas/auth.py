from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    username: str
    role: str
    role_label: str = Field(default="", description="The role, named for the interface")


class MeResponse(BaseModel):
    id: int
    username: str
    role: str
    role_label: str = Field(default="", description="The role, named for the interface")
