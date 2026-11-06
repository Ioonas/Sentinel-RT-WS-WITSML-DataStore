"""Tablas PostgreSQL del producto.

La integridad referencial entre objetos WITSML se valida en los casos de uso y
en la misma transacción; no se habilita borrado en cascada a nivel de base de
datos. La cascada WITSML (`cascadedDelete=true`) se resuelve en la capa de
aplicación para comprobar permisos y registrar `changeLog` (§6, §7).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class WitsmlObjectMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(128), nullable=False)
    uid_well: Mapped[str | None] = mapped_column(String(128))
    uid_wellbore: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str | None] = mapped_column(String(255))
    identity_key: Mapped[str] = mapped_column(String(640), nullable=False, unique=True)
    xml: Mapped[str] = mapped_column(Text, nullable=False)
    fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    d_tim_creation: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    d_tim_last_change: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    growing_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WellRow(WitsmlObjectMixin, Base):
    __tablename__ = "wells"
    __table_args__ = (Index("ix_wells_uid", "uid"),)


class WellboreRow(WitsmlObjectMixin, Base):
    __tablename__ = "wellbores"
    __table_args__ = (
        Index("ix_wellbores_uid_well", "uid_well"),
        Index("ix_wellbores_uid", "uid"),
    )


class LogRow(WitsmlObjectMixin, Base):
    __tablename__ = "logs"
    index_type: Mapped[str] = mapped_column(String(16), nullable=False)
    index_curve: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    start_index_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_index_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 15))
    end_index_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_index_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 15))
    index_uom: Mapped[str | None] = mapped_column(String(32))
    __table_args__ = (
        Index("ix_logs_uid_well_wellbore", "uid_well", "uid_wellbore"),
        Index("ix_logs_uid", "uid"),
    )
    curves: Mapped[list[LogCurveRow]] = relationship(
        back_populates="log", order_by="LogCurveRow.ordering"
    )


class LogCurveRow(Base):
    __tablename__ = "log_curves"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    log_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("logs.id", ondelete="RESTRICT"), nullable=False
    )
    mnemonic: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(64))
    curve_type: Mapped[str | None] = mapped_column(String(64))
    is_index: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text)
    curve_uid: Mapped[str | None] = mapped_column(String(128))
    ordering: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    log: Mapped[LogRow] = relationship(back_populates="curves")
    __table_args__ = (UniqueConstraint("log_id", "mnemonic", name="uq_log_curve_mnemonic"),)


class LogSampleRow(Base):
    __tablename__ = "log_samples"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    log_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("logs.id", ondelete="RESTRICT"), nullable=False
    )
    sample_order: Mapped[int] = mapped_column(BigInteger, nullable=False)
    index_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    index_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 15))
    values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (
        UniqueConstraint("log_id", "sample_order", name="uq_log_sample_order"),
        Index("ix_log_samples_log_time", "log_id", "index_time"),
        Index("ix_log_samples_log_value", "log_id", "index_value"),
    )


class TrajectoryRow(WitsmlObjectMixin, Base):
    __tablename__ = "trajectories"
    md_min: Mapped[Decimal | None] = mapped_column(Numeric(38, 15))
    md_max: Mapped[Decimal | None] = mapped_column(Numeric(38, 15))
    md_uom: Mapped[str | None] = mapped_column(String(32))
    __table_args__ = (
        Index("ix_trajectories_uid_well_wellbore", "uid_well", "uid_wellbore"),
    )


class TrajectoryStationRow(Base):
    __tablename__ = "trajectory_stations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trajectory_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trajectories.id", ondelete="RESTRICT"), nullable=False
    )
    station_order: Mapped[int] = mapped_column(Integer, nullable=False)
    md: Mapped[Decimal | None] = mapped_column(Numeric(38, 15))
    incl: Mapped[Decimal | None] = mapped_column(Numeric(38, 15))
    azi: Mapped[Decimal | None] = mapped_column(Numeric(38, 15))
    tvd: Mapped[Decimal | None] = mapped_column(Numeric(38, 15))
    xml: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        UniqueConstraint("trajectory_id", "station_order", name="uq_station_order"),
        Index("ix_stations_trajectory_md", "trajectory_id", "md"),
    )


class MudLogRow(WitsmlObjectMixin, Base):
    __tablename__ = "mud_logs"
    md_min: Mapped[Decimal | None] = mapped_column(Numeric(38, 15))
    md_max: Mapped[Decimal | None] = mapped_column(Numeric(38, 15))
    md_uom: Mapped[str | None] = mapped_column(String(32))
    __table_args__ = (
        Index("ix_mud_logs_uid_well_wellbore", "uid_well", "uid_wellbore"),
        Index("ix_mud_logs_uid", "uid"),
    )


class ChangeLogRow(Base):
    __tablename__ = "change_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(128), nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)
    change_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    uid_well: Mapped[str | None] = mapped_column(String(128))
    uid_wellbore: Mapped[str | None] = mapped_column(String(128))
    name_object: Mapped[str | None] = mapped_column(String(255))
    name_well: Mapped[str | None] = mapped_column(String(255))
    name_wellbore: Mapped[str | None] = mapped_column(String(255))
    change_info: Mapped[str | None] = mapped_column(Text)
    mnemonics: Mapped[str | None] = mapped_column(Text)
    start_index: Mapped[str | None] = mapped_column(String(64))
    end_index: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        Index("ix_change_log_object", "object_type", "uid"),
        Index("ix_change_log_date", "change_date"),
    )


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(32))
    object_uid: Mapped[str | None] = mapped_column(String(128))
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (
        Index("ix_audit_occurred", "occurred_at"),
        Index("ix_audit_actor", "actor_name"),
        Index("ix_audit_action", "action"),
        Index("ix_audit_correlation", "correlation_id"),
    )


class ServerConfigRow(Base):
    __tablename__ = "server_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    api_version: Mapped[str] = mapped_column(String(32), nullable=False)
    setup_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_data_nodes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_data_points: Mapped[int] = mapped_column(Integer, nullable=False)
    growing_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    change_detection_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_request_latest_values: Mapped[int] = mapped_column(Integer, nullable=False)
    cascaded_delete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    support_uom_conversion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[str | None] = mapped_column(String(255))


class AdminUserRow(Base):
    __tablename__ = "admin_users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    permissions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminSessionRow(Base):
    __tablename__ = "admin_sessions"
    token_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False
    )
    csrf_token: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    authenticated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_sessions_user", "user_id"),)


class InvitationRow(Base):
    __tablename__ = "invitations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    permissions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordResetRow(Base):
    __tablename__ = "password_resets"
    token_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ServiceAccountRow(Base):
    __tablename__ = "service_accounts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    credential_hash: Mapped[str | None] = mapped_column(Text)
    grants: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    well_scope: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    can_cascade_delete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    replaced_by_id: Mapped[str | None] = mapped_column(String(64))
    replacement_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MailOutboxRow(Base):
    __tablename__ = "mail_outbox"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_mail_pending", "status", "next_attempt_at"),)
