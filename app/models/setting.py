import uuid
from sqlalchemy import Column, Text, ForeignKey

from app.database import Base


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    key = Column(Text, unique=True, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=False)
    updated_by = Column(Text, ForeignKey("users.id"), nullable=True)

    def __repr__(self):
        return f"<Setting(key={self.key})>"
