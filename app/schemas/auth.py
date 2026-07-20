from pydantic import BaseModel
from typing import Optional


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    logout_other_devices: Optional[bool] = False


class ChangePasswordResponse(BaseModel):
    message: str
    access_token: str
    token_type: str = "bearer"