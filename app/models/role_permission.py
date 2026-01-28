import uuid
from sqlalchemy import Column, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    role_id = Column(Text, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(Text, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)

    # Relationships
    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")

    # Уникальное ограничение: одна роль не может иметь одно право дважды
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )

    def __repr__(self):
        return f"<RolePermission(role_id={self.role_id}, permission_id={self.permission_id})>"
