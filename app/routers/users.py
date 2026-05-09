from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import user_cache, user_list_cache
from app.core.security import decode_access_token, get_password_hash
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate

router = APIRouter(tags=["users"])


def get_current_user(authorization: str = Header(...), db: Session = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication")

    token = authorization.replace("Bearer ", "", 1)
    email = decode_access_token(token)
    if email is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    cache_key = f"user_email:{email}"
    cached = user_cache.get(cache_key)
    if cached is not None:
        return cached
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user_cache[cache_key] = user

    return user


@router.get("/users/me", response_model=UserResponse)
def get_current_user_info(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/users", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db)) -> list:
    cached = user_list_cache.get("all")
    if cached is not None:
        return cached
    users = db.query(User).all()
    user_list_cache["all"] = users
    return users


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
    db.refresh(user)
    user_cache[f"user_id:{user.id}"] = user
    user_cache[f"user_email:{user.email}"] = user
    user_list_cache.pop("all", None)
    return user


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: str, db: Session = Depends(get_db)) -> User:
    cache_key = f"user_id:{user_id}"
    cached = user_cache.get(cache_key)
    if cached is not None:
        return cached
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user_cache[cache_key] = user
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: str, user_in: UserUpdate, db: Session = Depends(get_db)) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = user_in.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"] is not None:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
    if "email" in update_data and update_data["email"] is not None:
        existing = db.query(User).filter(User.email == update_data["email"], User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use")

    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    user_cache[f"user_id:{user.id}"] = user
    user_cache[f"user_email:{user.email}"] = user
    user_list_cache.pop("all", None)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, db: Session = Depends(get_db)) -> None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    db.delete(user)
    db.commit()
    user_cache.pop(f"user_id:{user.id}", None)
    user_cache.pop(f"user_email:{user.email}", None)
    user_list_cache.pop("all", None)
