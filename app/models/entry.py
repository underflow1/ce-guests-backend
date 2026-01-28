import uuid
from sqlalchemy import Column, Text, ForeignKey, Index, Integer
from sqlalchemy.orm import relationship

from app.database import Base


class Entry(Base):
    __tablename__ = "entries"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(Text, nullable=False)
    responsible = Column(Text, nullable=True)
    datetime = Column(Text, nullable=False)  # ISO 8601 format: YYYY-MM-DDTHH:MM:SS
    created_by = Column(Text, ForeignKey("users.id"), nullable=False)
    created_at = Column(Text, nullable=False)  # ISO timestamp
    updated_at = Column(Text, nullable=True)  # ISO timestamp
    updated_by = Column(Text, ForeignKey("users.id"), nullable=True)
    deleted_at = Column(Text, nullable=True)  # ISO timestamp for soft delete
    deleted_by = Column(Text, ForeignKey("users.id"), nullable=True)
    is_completed = Column(Integer, nullable=False, default=0)  # 0/1 для отметки принятого гостя

    # Relationships
    creator = relationship("User", foreign_keys=[created_by], back_populates="entries_created")
    updater = relationship("User", foreign_keys=[updated_by], back_populates="entries_updated")
    deleter = relationship("User", foreign_keys=[deleted_by], back_populates="entries_deleted")

    # Index for datetime filtering
    __table_args__ = (
        Index("idx_entries_datetime", "datetime"),
    )

    def __repr__(self):
        return f"<Entry(id={self.id}, name={self.name}, datetime={self.datetime})>"
