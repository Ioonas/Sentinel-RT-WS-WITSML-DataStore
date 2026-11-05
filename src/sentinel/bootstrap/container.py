"""Composición de dependencias (wiring).

Solo este módulo conoce a la vez el núcleo y los adaptadores. Los adaptadores
de entrada reciben servicios ya construidos y no importan persistencia.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sentinel.audit_config.service import (
    AuditService,
    ConfigService,
    HealthService,
    MailService,
    SetupService,
)
from sentinel.bootstrap.settings import Settings
from sentinel.identity_access.passwords import Argon2PasswordHasher, Sha256TokenHasher
from sentinel.identity_access.service import IdentityService
from sentinel.mail_worker.probe import check_smtp
from sentinel.persistence.database import create_engine, create_session_factory
from sentinel.persistence.repositories import SqlAlchemyRepositories
from sentinel.shared.clock import Clock, SystemClock
from sentinel.shared.ids import IdGenerator, UuidGenerator
from sentinel.witsml_application.domain.uom import UomValidator
from sentinel.witsml_application.inventory import InventoryService
from sentinel.witsml_application.service import WitsmlStoreService
from sentinel.xml_schema.xsd import LxmlXsdValidator, PermissiveSchemaValidator


@dataclass
class RequestServices:
    session: AsyncSession
    repos: SqlAlchemyRepositories
    identities: IdentityService
    config: ConfigService
    audit: AuditService
    setup: SetupService
    mail: MailService
    witsml: WitsmlStoreService
    inventory: InventoryService
    health: HealthService


class Container:
    def __init__(
        self,
        settings: Settings,
        *,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
        smtp_check: Callable[[], None] | None = None,
    ) -> None:
        self.settings = settings
        self.clock = clock or SystemClock()
        self.smtp_check: Callable[[], None] = smtp_check or (
            lambda: check_smtp(settings)
        )
        self.ids = ids or UuidGenerator()
        self.engine = create_engine(settings.database_url)
        self.session_factory: async_sessionmaker[AsyncSession] = create_session_factory(
            self.engine
        )
        schema_dir = settings.resolved_schema_dir
        self.validator = (
            LxmlXsdValidator(schema_dir) if schema_dir else PermissiveSchemaValidator()
        )
        self.uom = UomValidator(schema_dir)
        self.hasher = Argon2PasswordHasher()
        self.token_hasher = Sha256TokenHasher()

    @asynccontextmanager
    async def request(self) -> AsyncIterator[RequestServices]:
        async with self.session_factory() as session:
            repos = SqlAlchemyRepositories(session)
            identities = IdentityService(
                repos.identities, self.hasher, self.token_hasher, self.clock, self.ids
            )
            config = ConfigService(repos.config, self.clock)
            audit = AuditService(repos.audit, self.clock)
            setup = SetupService(
                config, identities, audit, self.clock, smtp_check=self.smtp_check
            )
            mail = MailService(
                repos.mail, self.clock, self.ids, self.settings.public_base_url
            )
            witsml = WitsmlStoreService(
                wells=repos.wells,
                wellbores=repos.wellbores,
                logs=repos.logs,
                mud_logs=repos.mud_logs,
                trajectories=repos.trajectories,
                change_log=repos.change_log,
                config=config,
                audit=audit,
                clock=self.clock,
                ids=self.ids,
                validator=self.validator,
                uom=self.uom,
            )
            inventory = InventoryService(
                wells=repos.wells,
                wellbores=repos.wellbores,
                logs=repos.logs,
                mud_logs=repos.mud_logs,
                trajectories=repos.trajectories,
                change_log=repos.change_log,
            )
            health = HealthService(
                probe=repos.ping, mail=repos.mail, clock=self.clock
            )
            services = RequestServices(
                session=session,
                repos=repos,
                identities=identities,
                config=config,
                audit=audit,
                setup=setup,
                mail=mail,
                witsml=witsml,
                inventory=inventory,
                health=health,
            )
            try:
                yield services
            except Exception:
                await session.rollback()
                raise
            else:
                await session.commit()

    async def dispose(self) -> None:
        await self.engine.dispose()
