from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import declarative_base, relationship
import datetime

DATABASE_URL = "sqlite+aiosqlite:///fabrika.db"

Base = declarative_base()
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    notifications_enabled = Column(Boolean, default=True)
    subscriptions = relationship("Subscription", back_populates="user")
    orders = relationship("Order", back_populates="user")


class Week(Base):
    __tablename__ = "weeks"
    week_id = Column(String, primary_key=True)
    posts = relationship("Post", back_populates="week")


class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    week_id = Column(String, ForeignKey("weeks.week_id"))
    title = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    status = Column(String, default="draft")
    week = relationship("Week", back_populates="posts")
    edits = relationship("PostEdit", back_populates="post")


class PostEdit(Base):
    __tablename__ = "post_edits"
    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    post = relationship("Post", back_populates="edits")


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    start_date = Column(DateTime, default=datetime.datetime.utcnow)
    end_date = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="subscriptions")


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    product_name = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    status = Column(String, default="new")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship("User", back_populates="orders")


async def get_session():
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)