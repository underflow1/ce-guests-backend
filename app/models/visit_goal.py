import uuid
from sqlalchemy import Column, Text, Integer, Table, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


entry_visit_goals = Table(
    "entry_visit_goals",
    Base.metadata,
    Column("entry_id", Text, ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True),
    Column("visit_goal_id", Text, ForeignKey("visit_goals.id", ondelete="CASCADE"), primary_key=True),
)


class VisitGoal(Base):
    __tablename__ = "visit_goals"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(Text, unique=True, nullable=False)
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=True)
    updated_by = Column(Text, ForeignKey("users.id"), nullable=True)

    entries = relationship("Entry", secondary=entry_visit_goals, back_populates="visit_goals")

    def __repr__(self):
        return f"<VisitGoal(id={self.id}, name={self.name}, is_active={self.is_active})>"
