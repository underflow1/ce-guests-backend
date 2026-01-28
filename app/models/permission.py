import uuid
from sqlalchemy import Column, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(Text, unique=True, nullable=False, index=True)  # например "can_add", "can_delete"
    name = Column(Text, nullable=False)  # человекочитаемое название
    description = Column(Text, nullable=True)

    # Relationships
    role_permissions = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Permission(id={self.id}, code={self.code}, name={self.name})>"
