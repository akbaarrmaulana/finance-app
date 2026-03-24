from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    
    accounts: List["Account"] = Relationship(back_populates="user")
    transactions: List["Transaction"] = Relationship(back_populates="user")

class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    account_name: str
    account_type: str # e.g., 'Bank', 'Cash', 'E-Wallet'
    balance: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    user: Optional[User] = Relationship(back_populates="accounts")
    transactions: List["Transaction"] = Relationship(back_populates="account")

class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    account_id: int = Field(foreign_key="account.id")
    amount: float
    category: str
    type: str # 'Income' or 'Expense'
    date: datetime = Field(default_factory=datetime.utcnow)
    note: Optional[str] = Field(default=None)
    
    user: Optional[User] = Relationship(back_populates="transactions")
    account: Optional[Account] = Relationship(back_populates="transactions")
