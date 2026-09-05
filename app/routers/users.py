from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import user_cache, user_list_cache
from app.core.security import get_current_user, get_password_hash
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate

router = APIRouter(tags=["users"])


@router.get("/users/me", response_model=UserResponse)
def get_current_user_info(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/users", response_model=list[UserResponse])
def list_users(user: User = Depends(get_current_user)) -> list:
    return [user]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)) -> User:
    cache_key = f"user_email:{user_in.email}"
    existing = user_cache.get(cache_key) or db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        email=user_in.email,
        username=user_in.username,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
    )
    db.add(user)
    db.commit()
    user_cache[f"user_id:{user.id}"] = user
    user_cache[f"user_email:{user.email}"] = user
    user_list_cache.pop("all", None)
    return user


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: str, user: User = Depends(get_current_user)) -> User:
    if user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    if user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update your own account")
    update_data = user_in.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"] is not None:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
    if "email" in update_data and update_data["email"] is not None:
        existing = db.query(User).filter(User.email == update_data["email"], User.id != user.id).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use")

    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    user_cache[f"user_id:{user.id}"] = user
    user_cache[f"user_email:{user.email}"] = user
    user_list_cache.pop("all", None)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    if user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own account")

    db.delete(user)
    db.commit()
    user_cache.pop(f"user_id:{user.id}", None)
    user_cache.pop(f"user_email:{user.email}", None)
    user_list_cache.pop("all", None)
