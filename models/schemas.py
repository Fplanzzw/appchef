from typing import Optional, List

from pydantic import BaseModel, Field


# --- 数据模型 ---
class ChatRequest(BaseModel):
    message: str
    image_url: Optional[str] = None
    thread_id: str
    user_id: str = "default"
    lon: Optional[float] = Field(None, description="经度，用于高德逆地理编码")
    lat: Optional[float] = Field(None, description="纬度，用于高德逆地理编码")


class RecipeFeedbackRequest(BaseModel):
    thread_id: str
    user_id: str = "default"
    action: str = Field(..., description="reject、clarify 或 dislike")
    recipe_name: Optional[str] = Field(None, description="被反馈的菜名")
    recent_recipes: Optional[List[str]] = Field(None, description="近期推荐菜谱")
    user_clarification: Optional[str] = Field(None, description="用户补充说明")
    feedback_reason: Optional[str] = Field(None, description="反馈原因：口味不合/过敏/不喜欢/其他")


class IngredientConfirmRequest(BaseModel):
    thread_id: str
    user_id: str = "default"
    confirmed_ingredients: List[str] = Field(..., description="用户确认的食材列表")
    unknown_ingredients: List[str] = Field(default_factory=list, description="用户修正的未知食材")
    validation_type: str = Field("ingredient", description="验证类型：ingredient（食材验证）或 recipe（菜谱验证）")
    validation_reason: Optional[str] = Field(None, description="验证原因，如'未知食材'或'非食材'")
