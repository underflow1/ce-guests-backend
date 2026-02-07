import uuid
from sqlalchemy import Column, Text, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class MeetingResult(Base):
    __tablename__ = "meeting_results"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(Text, unique=True, nullable=False)
    code = Column(Integer, nullable=True)
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=True)
    updated_by = Column(Text, ForeignKey("users.id"), nullable=True)

    reasons = relationship("MeetingResultReason", back_populates="result")

    __table_args__ = (
        UniqueConstraint("name", name="uq_meeting_results_name"),
    )

    def __repr__(self):
        return f"<MeetingResult(id={self.id}, name={self.name}, is_active={self.is_active})>"
