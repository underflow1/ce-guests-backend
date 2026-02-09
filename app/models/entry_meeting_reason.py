from sqlalchemy import Column, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class EntryMeetingReason(Base):
    """
    Причина результата встречи для конкретной записи.

    Хранится отдельно от entries, чтобы entries оставалась "чистой":
    - результат фиксируется через entries.state (40/50/60)
    - причина хранится отдельно и нужна только для 40/50
    """

    __tablename__ = "entry_meeting_reasons"

    entry_id = Column(Text, ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True)
    reason_id = Column(Text, ForeignKey("reasons.id"), nullable=False)

    entry = relationship("Entry", back_populates="meeting_reason")
    reason = relationship("Reason")

    def __repr__(self):
        return f"<EntryMeetingReason(entry_id={self.entry_id}, reason_id={self.reason_id})>"

