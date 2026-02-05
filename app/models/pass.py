import uuid

from sqlalchemy import Column, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Pass(Base):
    __tablename__ = "passes"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    entry_id = Column(Text, ForeignKey("entries.id"), nullable=False, index=True)
    date = Column(Text, nullable=False)  # YYYY-MM-DD

    request_id = Column(Text, nullable=False)  # наш UUID для сопоставления во внешней системе
    external_id = Column(Text, nullable=True)  # ID во внешней системе (если получим)

    status = Column(Text, nullable=False, default="ordered")  # ordered|failed|revoked

    created_at = Column(Text, nullable=False)  # ISO timestamp
    updated_at = Column(Text, nullable=True)  # ISO timestamp
    updated_by = Column(Text, ForeignKey("users.id"), nullable=True)

    # Relationships
    entry = relationship("Entry", foreign_keys=[entry_id], back_populates="passes")
    updater = relationship("User", foreign_keys=[updated_by])

    __table_args__ = (
        Index("idx_passes_entry_date", "entry_id", "date"),
        Index("idx_passes_status", "status"),
    )

    def __repr__(self):
        return f"<Pass(id={self.id}, entry_id={self.entry_id}, date={self.date}, status={self.status})>"

