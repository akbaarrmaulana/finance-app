from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from typing import Optional
from datetime import datetime, timedelta

from api.database import create_db_and_tables, get_session
from api.models import User, Account, Transaction
from api.auth import sign_up as sb_sign_up, sign_in as sb_sign_in, get_supabase_user, reset_password_for_email, ACCESS_TOKEN_EXPIRE_MINUTES

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Base dir is /api, so we need to go up one level for templates/static
TEMPLATE_DIR = os.path.join(os.path.dirname(BASE_DIR), "templates")
STATIC_DIR = os.path.join(os.path.dirname(BASE_DIR), "static")

app = FastAPI(title="FinTracker Modern")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATE_DIR)

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# Dependency to get current user from cookies
def get_current_user(request: Request, session: Session = Depends(get_session)):
    token = request.cookies.get("access_token")
    if not token:
        return None
    
    if token.startswith("Bearer "):
        token = token.split(" ")[1]
        
    sb_user = get_supabase_user(token)
    if not sb_user:
        return None
        
    # Sync with local DB user
    statement = select(User).where(User.supabase_id == sb_user.id)
    user = session.exec(statement).first()
    
    if not user:
        # This shouldn't happen often if we sync on login, but for safety:
        user = User(
            supabase_id=sb_user.id,
            email=sb_user.email,
            username=sb_user.email.split('@')[0], # Fallback username
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        
    return user

def get_current_user_required(request: Request, session: Session = Depends(get_session)):
    user = get_current_user(request, session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": "/login"},
        )
    return user

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, current_user: Optional[User] = Depends(get_current_user)):
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request})

@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    try:
        auth_res = sb_sign_in(email, password)
        session_data = auth_res.session
        sb_user = auth_res.user
        
        # Check if login needs email confirmation
        if not sb_user:
            return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "error": "Login failed."})

        # Sync local user
        # 1. Try matching by supabase_id
        statement = select(User).where(User.supabase_id == sb_user.id)
        local_user = session.exec(statement).first()
        
        # 2. If not found by ID, try matching by email (linking old manual account)
        if not local_user:
            statement_email = select(User).where(User.email == sb_user.email)
            local_user = session.exec(statement_email).first()
            if local_user:
                # LINK existing account to Supabase
                local_user.supabase_id = sb_user.id
                session.add(local_user)
                session.commit()
            else:
                # CREATE new if actually new
                local_user = User(
                    supabase_id=sb_user.id,
                    email=sb_user.email,
                    username=sb_user.email.split('@')[0]
                )
                session.add(local_user)
                session.commit()

        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="access_token", 
            value=f"Bearer {session_data.access_token}", 
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax",
            secure=True 
        )
        return response
    except Exception as e:
        err_msg = str(e)
        if "Email not confirmed" in err_msg:
            err_msg = "Please confirm your email address before logging in."
        elif "Invalid login credentials" in err_msg:
            err_msg = "Invalid email or password."
        return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "error": err_msg})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html", context={"request": request})

@app.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    try:
        # Sign up in Supabase
        sb_sign_up(email, password)
        
        # We don't create local user yet, we wait for login confirm
        return templates.TemplateResponse(request=request, name="login.html", context={
            "request": request, 
            "success": "Registration successful! Please check your email for verification link."
        })
    except Exception as e:
        return templates.TemplateResponse(request=request, name="register.html", context={"request": request, "error": str(e)})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user: User = Depends(get_current_user_required)):
    return templates.TemplateResponse(request=request, name="profile.html", context={"request": request, "user": user})

@app.post("/profile/update")
async def update_profile(
    request: Request,
    username: str = Form(None),
    full_name: str = Form(None),
    profile_photo_url: str = Form(None),
    user: User = Depends(get_current_user_required),
    session: Session = Depends(get_session)
):
    user.username = username or user.username
    user.full_name = full_name
    user.profile_photo_url = profile_photo_url
    session.add(user)
    session.commit()
    return RedirectResponse(url="/profile", status_code=status.HTTP_302_FOUND)

@app.post("/profile/reset-password")
async def reset_password(
    request: Request,
    user: User = Depends(get_current_user_required)
):
    try:
        # We now use our lightweight httpx helper
        reset_password_for_email(user.email)
        return templates.TemplateResponse(request=request, name="profile.html", context={
            "request": request, 
            "user": user,
            "success": "Password reset link sent to your email!"
        })
    except Exception as e:
        return templates.TemplateResponse(request=request, name="profile.html", context={
            "request": request, 
            "user": user,
            "error": str(e)
        })

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request, 
    period: str = "month",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    account_id: Optional[str] = "all",
    user: User = Depends(get_current_user_required),
    session: Session = Depends(get_session)
):
    # Fetch user accounts
    accounts = session.exec(select(Account).where(Account.user_id == user.id)).all()
    
    # Calculate date filtering
    now = datetime.utcnow()
    query = select(Transaction).where(Transaction.user_id == user.id)
    
    if account_id and account_id != "all":
        try:
            acc_id_int = int(account_id)
            query = query.where(Transaction.account_id == acc_id_int)
        except ValueError:
            pass
    
    if period == 'today':
        st_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.where(Transaction.date >= st_date)
    elif period == 'week':
        st_date = now - timedelta(days=now.weekday())
        st_date = st_date.replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.where(Transaction.date >= st_date)
    elif period == 'month':
        st_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        query = query.where(Transaction.date >= st_date)
    elif period == 'year':
        st_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        query = query.where(Transaction.date >= st_date)
    elif period == 'custom' and start_date and end_date:
        try:
            st = datetime.strptime(start_date, "%Y-%m-%d")
            en = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            query = query.where(Transaction.date >= st).where(Transaction.date <= en)
        except ValueError:
            pass
            
    # All transactions in the current period
    all_tx = session.exec(query.order_by(Transaction.date.desc())).all()
    
    # Fetch recent transactions independently of filter
    statement = select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.date.desc()).limit(10)
    recent_transactions = session.exec(statement).all()
    
    total_balance = sum(acc.balance for acc in accounts)
    
    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "request": request, 
        "user": user, 
        "accounts": accounts, 
        "transactions": all_tx,
        "recent_transactions": recent_transactions,
        "total_balance": total_balance,
        "period": period,
        "start_date": start_date or "",
        "end_date": end_date or "",
        "account_id": account_id or "all"
    })

@app.get("/accounts", response_class=HTMLResponse)
async def accounts_page(request: Request, user: User = Depends(get_current_user_required), session: Session = Depends(get_session)):
    accounts = session.exec(select(Account).where(Account.user_id == user.id)).all()
    return templates.TemplateResponse(request=request, name="accounts.html", context={"request": request, "user": user, "accounts": accounts})

@app.post("/accounts/add")
async def add_account(
    request: Request,
    account_name: str = Form(...),
    account_type: str = Form(...), # e.g. BCA, Dompet, OVO
    initial_balance: float = Form(default=0.0),
    user: User = Depends(get_current_user_required),
    session: Session = Depends(get_session)
):
    account = Account(
        user_id=user.id,
        account_name=account_name,
        account_type=account_type,
        balance=initial_balance
    )
    session.add(account)
    session.commit()
    return RedirectResponse(url="/accounts", status_code=status.HTTP_302_FOUND)

@app.post("/accounts/delete/{account_id}")
async def delete_account(
    account_id: int,
    user: User = Depends(get_current_user_required),
    session: Session = Depends(get_session)
):
    account = session.get(Account, account_id)
    if account and account.user_id == user.id:
        # Before deleting, also need to handle transactions? 
        # For simple app, just delete account and cascade or delete transactions manually
        transactions = session.exec(select(Transaction).where(Transaction.account_id == account_id)).all()
        for t in transactions:
            session.delete(t)
        session.delete(account)
        session.commit()
    return RedirectResponse(url="/accounts", status_code=status.HTTP_302_FOUND)

@app.get("/transactions", response_class=HTMLResponse)
async def transactions_page(request: Request, user: User = Depends(get_current_user_required), session: Session = Depends(get_session)):
    accounts = session.exec(select(Account).where(Account.user_id == user.id)).all()
    transactions = session.exec(select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.date.desc())).all()
    return templates.TemplateResponse(request=request, name="transactions.html", context={"request": request, "user": user, "accounts": accounts, "transactions": transactions})

@app.post("/accounts/edit/{account_id}")
async def edit_wallet(
    request: Request,
    account_id: int,
    account_name: str = Form(...),
    initial_balance: float = Form(...),
    user: User = Depends(get_current_user_required),
    session: Session = Depends(get_session)
):
    account = session.get(Account, account_id)
    if account and account.user_id == user.id:
        account.account_name = account_name
        account.balance = initial_balance
        session.add(account)
        session.commit()
    return RedirectResponse(url="/accounts", status_code=status.HTTP_302_FOUND)

@app.post("/transactions/add")
async def add_transaction(
    request: Request,
    account_id: int = Form(...),
    amount: float = Form(...),
    type: str = Form(...), # 'Income', 'Expense', or 'Transfer'
    category: Optional[str] = Form(default="Transfer"),
    to_account_id: Optional[int] = Form(default=None),
    note: str = Form(default=""),
    source: Optional[str] = Form(default=None),
    user: User = Depends(get_current_user_required),
    session: Session = Depends(get_session)
):
    redirect_url = "/dashboard" if source == "dashboard" else "/transactions"

    if amount < 0:
        amount = abs(amount) # Ensure positive input
        
    account = session.get(Account, account_id)
    if not account or account.user_id != user.id:
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
        
    if type == "Transfer":
        account_to = session.get(Account, to_account_id)
        if not account_to or account_to.user_id != user.id or account.id == account_to.id:
            return RedirectResponse(url="/transactions", status_code=status.HTTP_302_FOUND)
            
        account.balance -= amount
        account_to.balance += amount
        
        tx_str_note = f"| {note}" if note else ""
        tx_out = Transaction(user_id=user.id, account_id=account.id, amount=amount, category="Transfer Out", type="Transfer", note=f"To {account_to.account_name} {tx_str_note}".strip())
        tx_in = Transaction(user_id=user.id, account_id=account_to.id, amount=amount, category="Transfer In", type="Transfer", note=f"From {account.account_name} {tx_str_note}".strip())
        
        session.add(account)
        session.add(account_to)
        session.add(tx_out)
        session.add(tx_in)
        session.commit()
    else:
        # Update account balance
        if type == "Expense":
            account.balance -= amount
        elif type == "Income":
            account.balance += amount
            
        session.add(account)
        
        transaction = Transaction(
            user_id=user.id,
            account_id=account_id,
            amount=amount,
            category=category or "Other",
            type=type,
            note=note
        )
        session.add(transaction)
        session.commit()
    
    return RedirectResponse(url="/transactions", status_code=status.HTTP_302_FOUND)
