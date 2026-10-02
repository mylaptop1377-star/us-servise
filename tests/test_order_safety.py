import unittest

import aiohttp
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.config import Settings
from bot.database.engine import create_database
from bot.database.models import Base, Package, User
from bot.database.requests import create_order, get_order_stats, transition_order, list_packages
from bot.handlers.common import is_admin
from bot.services.midasbuy import MidasbuyClient


class OrderSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_only_one_admin_can_transition_pending_order(self) -> None:
        async with self.sessions.begin() as session:
            user = User(id=101, username=None, full_name="Buyer")
            package = Package(name="60 UC", uc_amount=60, price=12000, is_active=True)
            session.add_all([user, package])
            await session.flush()

        package = await self._package()
        order = await create_order(
            self.sessions,
            user_id=101,
            package=package,
            player_id="123456",
            player_nickname="PLAYER",
            receipt_file_id="telegram-file-id",
            receipt_kind="photo",
        )

        self.assertTrue(
            await transition_order(
                self.sessions,
                order.id,
                expected_status="PENDING",
                new_status="APPROVED",
                reviewer_id=201,
            )
        )
        self.assertFalse(
            await transition_order(
                self.sessions,
                order.id,
                expected_status="PENDING",
                new_status="REJECTED",
                reviewer_id=202,
                reason="duplicate action",
            )
        )
        self.assertEqual(await get_order_stats(self.sessions), (1, 0, 12000))

    async def test_admin_authorization_uses_exact_numeric_id(self) -> None:
        admin = TelegramUser(id=201, is_bot=False, first_name="Admin")
        other_user = TelegramUser(id=202, is_bot=False, first_name="User")
        self.assertTrue(is_admin(admin, frozenset({201})))
        self.assertFalse(is_admin(other_user, frozenset({201})))

    async def test_invalid_order_transition_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            await transition_order(
                self.sessions,
                1,
                expected_status="APPROVED",
                new_status="REJECTED",
                reviewer_id=201,
                reason="not allowed",
            )
        with self.assertRaises(ValueError):
            await transition_order(
                self.sessions,
                1,
                expected_status="PENDING",
                new_status="REJECTED",
                reviewer_id=201,
            )

    async def test_startup_initializes_schema_and_sample_packages(self) -> None:
        sessions, engine = await create_database("sqlite+aiosqlite:///:memory:")
        try:
            packages = await list_packages(sessions)
            self.assertEqual([package.uc_amount for package in packages], [60, 325, 660, 1800])
        finally:
            await engine.dispose()

    async def test_mock_provider_does_not_confirm_real_fulfillment(self) -> None:
        settings = Settings(
            bot_token="",
            admin_ids=frozenset(),
            database_url="sqlite+aiosqlite:///:memory:",
            midasbuy_mode="mock",
            midasbuy_lookup_url=None,
            uc_fulfillment_url=None,
            midasbuy_api_token=None,
        )
        async with aiohttp.ClientSession() as http_session:
            provider = MidasbuyClient(http_session, settings)
            self.assertEqual(await provider.lookup_player("123456"), "TEST_PLAYER_123456")
            result = await provider.fulfill(order_id=1, player_id="123456", uc_amount=60)
        self.assertFalse(result.confirmed)
        self.assertTrue(result.simulated)

    async def _package(self) -> Package:
        async with self.sessions() as session:
            return await session.get(Package, 1)


if __name__ == "__main__":
    unittest.main()
