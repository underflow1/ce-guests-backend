import uuid
from sqlalchemy import Column, Text, Integer
from sqlalchemy.orm import relationship

from app.database import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(Text, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    interface_type = Column(Text, nullable=False, default="user")  # "user" or "guard"
    created_at = Column(Text, nullable=False)

    # Relationships
    users = relationship("User", back_populates="role")
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Role(id={self.id}, name={self.name}, interface_type={self.interface_type})>"
