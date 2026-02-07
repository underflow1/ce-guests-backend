import uuid
from sqlalchemy import Column, Text, ForeignKey, Index, Integer
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.visit_goal import entry_visit_goals


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
    # Состояние записи (основной первоисточник бизнес-логики)
    # 10=черновик, 20=отменена, 30=гость принят, 40=отказ, 50=не оформлен, 60=трудоустроен
    state = Column(Integer, nullable=False, default=10)

    # Текущий пропуск (может быть revoked/failed — это история, не признак "активности")
    current_pass_id = Column(Text, ForeignKey("passes.id"), nullable=True)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by], back_populates="entries_created")
    updater = relationship("User", foreign_keys=[updated_by], back_populates="entries_updated")
    deleter = relationship("User", foreign_keys=[deleted_by], back_populates="entries_deleted")

    passes = relationship("Pass", foreign_keys="Pass.entry_id", back_populates="entry")
    current_pass = relationship("Pass", foreign_keys=[current_pass_id])
    visit_goals = relationship("VisitGoal", secondary=entry_visit_goals, back_populates="entries")
    meeting_reason = relationship(
        "EntryMeetingReason",
        uselist=False,
        back_populates="entry",
        cascade="all, delete-orphan",
    )

    # Index for datetime filtering
    __table_args__ = (
        Index("idx_entries_datetime", "datetime"),
    )

    def __repr__(self):
        return f"<Entry(id={self.id}, name={self.name}, datetime={self.datetime})>"
