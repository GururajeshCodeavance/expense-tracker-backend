from models import User, Expense
from auth import hash_password, verify_password, create_access_token
from datetime import datetime, timedelta
from sqlalchemy import func, extract
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
import calendar

def create_user(db, user):
    try:
        new_user = User(
            name=user.name,
            email=user.email,
            password=hash_password(user.password)
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")

def login_user(db, user):
    db_user = db.query(User).filter(User.email == user.email).first()
    # AFTER SUCCESS LOGIN
    create_log(db, db_user.id, "LOGIN", f"{db_user.email} logged in")

    if not db_user:
        return {"error": "User not found"}

    if not verify_password(user.password, db_user.password):
        return {"error": "Invalid password"}

    # 🔐 CREATE TOKEN
    token = create_access_token({"sub": db_user.email})

    return {
        "access_token": token,
        "token_type": "bearer"
    }

from models import ActivityLog

def create_log(db, user_id, action, description):
    log = ActivityLog(
        user_id=user_id,
        action=action,
        description=description
    )
    db.add(log)
    db.commit()

def get_total_expense(db, user_id):
    return db.query(func.sum(Expense.amount))\
        .filter(Expense.user_id == user_id)\
        .scalar() or 0


def get_highest_expense(db, user_id):
    return db.query(func.max(Expense.amount))\
        .filter(Expense.user_id == user_id)\
        .scalar() or 0


def get_category_breakdown(db, user_id):
    results = db.query(
        Expense.category,
        func.sum(Expense.amount)
    ).filter(
        Expense.user_id == user_id
    ).group_by(
        Expense.category
    ).order_by(
        func.sum(Expense.amount).desc()).all()

    return [
        {"category": r[0], "total": r[1]}
        for r in results
    ]

def get_monthly_summary(db, user_id):
    results = db.query(
        extract('month', Expense.created_at).label('month'),
        func.sum(Expense.amount)
    ).filter(
        Expense.user_id == user_id
    ).group_by(
        extract('month', Expense.created_at)
    ).order_by('month').all()

    return [
        {
            "month": calendar.month_name[int(r[0])],
            "total": r[1]
        }
        for r in results
    ]

def get_recent_expenses(db, user_id):
    return db.query(Expense)\
        .filter(Expense.user_id == user_id)\
        .order_by(Expense.created_at.desc())\
        .limit(5).all()

def get_top_category(db, user_id):
    result = db.query(
        Expense.category,
        func.sum(Expense.amount)
    ).filter(
        Expense.user_id == user_id
    ).group_by(
        Expense.category
    ).order_by(
        func.sum(Expense.amount).desc()
    ).first()

    return {
        "category": result[0],
        "total": result[1]
    } if result else None


def create_expense(db, expense, user_id):
    db_expense = Expense(
        title=expense.title,
        amount=expense.amount,
        category=expense.category,
        user_id=user_id   # 🔥 link to user
    )


    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)

    create_log(db, user_id, "ADD_EXPENSE",
               f"Added {expense.category} - ₹{expense.amount}")

    return db_expense

def get_expenses(db, user_id, category=None, start_date=None, end_date=None, search=None, sort_by=None, skip=0, limit=10):
    if user_id:
        query = db.query(Expense).filter(Expense.user_id == user_id)
    else:
        query = db.query(Expense)

    # Category filter
    if category:
        query = query.filter(Expense.category == category)

    # Date filters
    if start_date:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_date = datetime.combine(start_date, datetime.min.time())

        query = query.filter(Expense.created_at >= start_date)

    if end_date:
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end_date = datetime.combine(end_date, datetime.min.time())

        end_date = end_date + timedelta(days=1)
        query = query.filter(Expense.created_at < end_date)

        # NEW: Search (title)
    if search:
        query = query.filter(Expense.title.ilike(f"%{search}%"))

        #  NEW: Sorting
    if sort_by == "amount_desc":
        query = query.order_by(Expense.amount.desc())
    elif sort_by == "amount_asc":
        query = query.order_by(Expense.amount.asc())
    else:
        query = query.order_by(Expense.created_at.desc())  # default

        #  NEW: Total count
    total = query.count()

    # Pagination
    expenses = query.offset(skip).limit(limit).all()

    # NEW: Clean response format
    data = [
        {
            "id": e.id,
            "title": e.title,
            "amount": e.amount,
            "category": e.category,
            "date": e.created_at
        }
        for e in expenses
    ]

    #  FINAL RETURN
    return {
        "total": total,
        "data": data
    }

def get_monthly_report(db, user_id):
    results = db.query(
        extract('month', Expense.created_at).label('month'),
        func.sum(Expense.amount)
    ).filter(
        Expense.user_id == user_id
    ).group_by(
        extract('month', Expense.created_at)
    ).order_by('month').all()

    return [
        {
            "month": calendar.month_name[int(r[0])],
            "total": r[1]
        }
        for r in results
    ]

def get_highest_expense_report(db, user_id):
    expense = db.query(Expense)\
        .filter(Expense.user_id == user_id)\
        .order_by(Expense.amount.desc())\
        .first()

    if not expense:
        return None

    return {
        "title": expense.title,
        "amount": expense.amount,
        "category": expense.category,
        "date": expense.created_at
    }

def get_category_report(db, user_id):
    results = db.query(
        Expense.category,
        func.sum(Expense.amount)
    ).filter(
        Expense.user_id == user_id
    ).group_by(
        Expense.category
    ).order_by(
        func.sum(Expense.amount).desc()
    ).all()

    return [
        {
            "category": r[0],
            "total": r[1]
        }
        for r in results
    ]

def update_expense(db, expense_id, user_id, updated_data):
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.user_id == user_id
    ).first()


    if not expense:
        return None

    create_log(db, user_id, "UPDATE_EXPENSE",
               f"Updated expense ID {expense_id}")

    expense.title = updated_data.title
    expense.amount = updated_data.amount
    expense.category = updated_data.category

    db.commit()
    db.refresh(expense)

    return expense

def delete_expense(db, expense_id, user_id):
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.user_id == user_id
    ).first()

    if not expense:
        return None

    create_log(
        db,
        user_id,
        action="DELETE_EXPENSE",
        description=f"Deleted expense ID {expense_id}"
    )

    db.delete(expense)
    db.commit()

    return expense