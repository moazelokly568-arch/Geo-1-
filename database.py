from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class PlanConfig(Base):
    __tablename__ = "plan_configs"
    id = Column(Integer, primary_key=True, index=True)
    plan_code = Column(String(32), unique=True, nullable=False)
    daily_requests_limit = Column(Integer, nullable=False, default=10)
    max_file_mb = Column(Integer, nullable=False, default=5)
    allow_dxf_export = Column(Boolean, default=True)
    allow_gis_overlay = Column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(32), default="student")
    plan_code = Column(String(32), default="free")
    subscription_expires_at = Column(DateTime, nullable=True)
    daily_used_count = Column(Integer, default=0)
    last_usage_date = Column(String(16), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("ChatSession", back_populates="user")
    files = relationship("GeneratedFile", back_populates="user")


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    title = Column(String(255), default="محادثة هندسية")
    mode = Column(String(32), default="assistant")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.id"))
    role = Column(String(16))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")


class GeneratedFile(Base):
    __tablename__ = "generated_files"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(32), nullable=False)
    file_path = Column(String(512), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="files")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(255), default="guest")
    action = Column(String(128))
    status = Column(String(32))
    details = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(PlanConfig).filter_by(plan_code="free").first():
            db.add(PlanConfig(plan_code="free", daily_requests_limit=settings.FREE_DAILY_REQUESTS, max_file_mb=settings.FREE_MAX_FILE_MB))
        if not db.query(PlanConfig).filter_by(plan_code="pro").first():
            db.add(PlanConfig(plan_code="pro", daily_requests_limit=settings.PRO_DAILY_REQUESTS, max_file_mb=settings.PRO_MAX_FILE_MB))
        db.commit()
    finally:
        db.close()
