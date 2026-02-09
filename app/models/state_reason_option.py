from sqlalchemy import Column, Text, Integer, ForeignKey, UniqueConstraint

from app.database import Base


class StateReasonOption(Base):
    """Какие причины разрешены для конкретного state."""

    __tablename__ = "state_reason_options"

    state = Column(Integer, primary_key=True, nullable=False)
    reason_id = Column(Text, ForeignKey("reasons.id", ondelete="CASCADE"), primary_key=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("state", "reason_id", name="uq_state_reason_options_state_reason"),
    )

