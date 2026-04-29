from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: int
    username: str
    coins: int
    streak: int
    attribute_perception: int
    attribute_strength: int
    attribute_intelligence: int
    attribute_charm: int

    class Config:
        from_attributes = True
