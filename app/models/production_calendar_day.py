import uuid
from sqlalchemy import Boolean, Column, Index, Integer, Text

from app.database import Base


class ProductionCalendarDay(Base):
    __tablename__ = "production_calendar_days"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    date = Column(Text, nullable=False, unique=True)  # YYYY-MM-DD
    year = Column(Integer, nullable=False, index=True)
    is_workday = Column(Boolean, nullable=False)

    __table_args__ = (
        Index("idx_production_calendar_days_year", "year"),
    )

    def __repr__(self):
        return f"<ProductionCalendarDay(date={self.date}, is_workday={self.is_workday})>"
