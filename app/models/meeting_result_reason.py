import uuid
from sqlalchemy import Column, Text, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class MeetingResultReason(Base):
    __tablename__ = "meeting_result_reasons"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_result_id = Column(Text, ForeignKey("meeting_results.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=True)
    updated_by = Column(Text, ForeignKey("users.id"), nullable=True)

    result = relationship("MeetingResult", back_populates="reasons")

    __table_args__ = (
        UniqueConstraint("meeting_result_id", "name", name="uq_meeting_result_reason_name"),
    )

    def __repr__(self):
        return (
            f"<MeetingResultReason(id={self.id}, meeting_result_id={self.meeting_result_id}, "
            f"name={self.name}, is_active={self.is_active})>"
        )
