import uuid
from sqlalchemy import Column, Text, Integer, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(Text, nullable=False, index=True)
    expires_at = Column(Text, nullable=False)
    created_at = Column(Text, nullable=False)
    revoked = Column(Integer, nullable=False, default=0)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, revoked={self.revoked})>"
