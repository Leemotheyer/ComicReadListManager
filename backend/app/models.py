from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    comicvine_api_key: Mapped[str] = mapped_column(String(255), default="")
    kapowarr_url: Mapped[str] = mapped_column(String(512), default="http://localhost:5656")
    kapowarr_api_key: Mapped[str] = mapped_column(String(255), default="")
    kapowarr_root_folder_id: Mapped[int] = mapped_column(Integer, default=1)
    komga_url: Mapped[str] = mapped_column(String(512), default="http://localhost:25600")
    komga_api_key: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ReadList(Base):
    __tablename__ = "read_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    last_exported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    items: Mapped[list["ReadListItem"]] = relationship(
        "ReadListItem",
        back_populates="read_list",
        cascade="all, delete-orphan",
        order_by="ReadListItem.sort_order",
    )


class ReadListItem(Base):
    __tablename__ = "read_list_items"
    __table_args__ = (UniqueConstraint("list_id", "cv_issue_id", name="uq_list_issue"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("read_lists.id", ondelete="CASCADE"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cv_volume_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cv_issue_id: Mapped[int] = mapped_column(Integer, nullable=False)
    series: Mapped[str] = mapped_column(String(512), nullable=False)
    issue_number: Mapped[str] = mapped_column(String(64), nullable=False)
    volume_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cover_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issue_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    read_list: Mapped["ReadList"] = relationship("ReadList", back_populates="items")
