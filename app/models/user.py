import uuid
from datetime import datetime
from sqlalchemy import Column, Text, Integer, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(Text, unique=True, nullable=False, index=True)
    email = Column(Text, unique=True, nullable=True, index=True)
    full_name = Column(Text, nullable=True)
    password_hash = Column(Text, nullable=False)
    is_admin = Column(Integer, nullable=False, default=0)
    is_active = Column(Integer, nullable=False, default=1)
    role_id = Column(Text, ForeignKey("roles.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(Text, nullable=False)

    # Relationships
    role = relationship("Role", back_populates="users")
    entries_created = relationship("Entry", foreign_keys="Entry.created_by", back_populates="creator")
    entries_updated = relationship("Entry", foreign_keys="Entry.updated_by", back_populates="updater")
    entries_deleted = relationship("Entry", foreign_keys="Entry.deleted_by", back_populates="deleter")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, is_admin={self.is_admin})>"
