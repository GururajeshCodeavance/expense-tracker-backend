from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import engine, Base
from models import User
from schemas import UserCreate, UserResponse, UserLogin, ExpenseCreate
from crud import create_user, login_user, create_expense, get_expenses, update_expense,delete_expense, get_monthly_report, get_highest_expense_report, get_category_report
from crud import  get_total_expense, get_highest_expense, get_category_breakdown, get_monthly_summary, get_recent_expenses, get_top_category
from dependencies import get_db, get_current_user
from fastapi.security import OAuth2PasswordRequestForm
from typing import Optional
from datetime import datetime
import logging
from models import ActivityLog

logging.basicConfig(level=logging.INFO)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

@app.get("/")
def home():
    return {"message": "welcome to Expense Tracker"}

@app.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    logging.info(f"New user registering: {user.email}")
    return create_user(db, user)

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    logging.info(f"Login attempt: {form_data.username}")
    user_data = UserLogin(email=form_data.username,
        password=form_data.password)
    return login_user(db, user_data)

@app.get("/admin/logs")
def get_logs(
    action: Optional[str] = None,
    skip: int = 0,          # ✅ NEW
    limit: int = 5,         # ✅ NEW
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    query = db.query(ActivityLog)

    if action:
        query = query.filter(ActivityLog.action == action)

    total = query.count()   # ✅ TOTAL COUNT

    logs = query.order_by(ActivityLog.timestamp.desc())\
                .offset(skip)\
                .limit(limit)\
                .all()

    result = []
    for log in logs:
        user = db.query(User).filter(User.id == log.user_id).first()

        result.append({
            "email": user.email if user else "Unknown",
            "action": log.action,
            "description": log.description,
            "time": log.timestamp
        })

    return {
        "total": total,     # ✅ send total
        "data": result
    }

@app.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@app.get("/dashboard")
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    logging.info(f"User {current_user.id} accessed dashboard")
    user_id = current_user.id
    total = get_total_expense(db, user_id)
    highest = get_highest_expense(db, user_id)
    category = get_category_breakdown(db, user_id)
    monthly = get_monthly_summary(db, user_id)
    recent = get_recent_expenses(db, user_id)
    recent_data = [
        {
            "id": e.id,
            "title": e.title,
            "amount": e.amount
        }
        for e in recent
    ]
    top_category = get_top_category(db, user_id)
    return {
        "total": total,
        "highest": highest,
        "category_breakdown": category,
        "monthly_summary": monthly,
        "recent": recent_data,
        "top_category": top_category

    }

ALLOWED_CATEGORIES = ["food", "travel", "shopping", "bills", "subscription", "internet", "recharge","medicine", "other"]
@app.post("/expenses")
def add_expense(
    expense: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    logging.info(f"User {current_user.id} adding expense")

    if expense.amount > 10000:
        logging.warning(f"High expense: {expense.amount} by user {current_user.id}")
    # AMOUNT VALIDATION
    if expense.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")

    # Category validation
    if expense.category.lower() not in ALLOWED_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Allowed: {ALLOWED_CATEGORIES}"
        )
    return create_expense(db, expense, current_user.id)

@app.get("/expenses")
def read_expenses(
    category: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = None,
    skip: int = 0,
    limit: int = 10,
    show_all: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):

    logging.info(f"User {current_user.id} fetching expenses")

    if show_all and current_user.role != "admin":
        logging.warning(f"Unauthorized access by user {current_user.id}")
        raise HTTPException(status_code=403, detail="Not authorized")
    if current_user.role == "admin" and show_all:
        user_id = None
    else:
        user_id = current_user.id
    return get_expenses(db, user_id, category, start_date, end_date, search, sort_by, skip, limit)


@app.get("/reports/monthly")
def monthly_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    logging.info(f"User {current_user.id} requested monthly report")
    return get_monthly_report(db, current_user.id)

@app.get("/reports/highest")
def highest_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    logging.info(f"User {current_user.id} requested highest report")
    return get_highest_expense_report(db, current_user.id)

@app.get("/reports/category")
def category_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    logging.info(f"User {current_user.id} requested category report")
    return get_category_report(db, current_user.id)

@app.put("/expenses/{expense_id}")
def update_expense_api(
    expense_id: int,
    updated_data: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    logging.info(f"User {current_user.id} updating expense {expense_id}")
    updated = update_expense(db, expense_id, current_user.id, updated_data)

    if not updated:
        raise HTTPException(status_code=404, detail="Expense not found")

    return updated

@app.delete("/expenses/{expense_id}")
def delete_expense_api(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    logging.info(f"User {current_user.id} deleting expense {expense_id}")
    deleted = delete_expense(db, expense_id, current_user.id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Expense not found")

    return {"message": "Expense deleted successfully"}