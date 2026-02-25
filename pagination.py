from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter()

class User(BaseModel):
    id: int
    username: str
    status: str
    last_active: str

# Mock data - في الإنتاج تستخدم قاعدة البيانات
users_data = [
    {"id": i, "username": f"user_{i}", "status": "active", "last_active": "2024-02-25 10:30:00"} 
    for i in range(1, 251)  # 250 مستخدم للتجربة
]

@router.get("/api/users", response_model=List[User])
async def get_users(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page")
):
    start = (page - 1) * per_page
    end = start + per_page
    users = users_data[start:end]
    return users

@router.get("/api/users/count")
async def get_users_count():
    return {"total": len(users_data)}
