from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    username: str
    role_news: str = Field(
        description="The role the person holds in the News Feed",
    )
    role_news_label: str = Field(
        default="",
        description="The News Feed role, named for the interface",
    )
    role_bench: str = Field(
        description="The role the person holds in Peer Benchmarking",
    )
    role_bench_label: str = Field(
        default="",
        description="The Peer Benchmarking role, named for the interface",
    )


class MeResponse(BaseModel):
    id: int
    username: str
    role_news: str = Field(
        description="The role the person holds in the News Feed",
    )
    role_news_label: str = Field(
        default="",
        description="The News Feed role, named for the interface",
    )
    role_bench: str = Field(
        description="The role the person holds in Peer Benchmarking",
    )
    role_bench_label: str = Field(
        default="",
        description="The Peer Benchmarking role, named for the interface",
    )
