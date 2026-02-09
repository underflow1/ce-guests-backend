import uuid

from sqlalchemy import Column, Text, Integer, ForeignKey, UniqueConstraint

from app.database import Base


class Reason(Base):
    """Единый справочник причин (переиспользуется между state)."""

    __tablename__ = "reasons"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(Text, nullable=False, unique=True)
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=True)
    updated_by = Column(Text, ForeignKey("users.id"), nullable=True)

    def __repr__(self):
        return f"<Reason(id={self.id}, name={self.name}, is_active={self.is_active})>"

