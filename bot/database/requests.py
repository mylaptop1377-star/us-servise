from decimal import Decimal

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.database.models import Order, Package, Setting, User


async def upsert_user(
    sessions: async_sessionmaker[AsyncSession],
    user_id: int,
    username: str | None,
    full_name: str,
) -> None:
    async with sessions.begin() as session:
        user = await session.get(User, user_id)
        if user is None:
            session.add(User(id=user_id, username=username, full_name=full_name))
        else:
            user.username = username
            user.full_name = full_name


async def get_user(sessions: async_sessionmaker[AsyncSession], user_id: int) -> User | None:
    async with sessions() as session:
        return await session.get(User, user_id)


async def list_packages(
    sessions: async_sessionmaker[AsyncSession], active_only: bool = True
) -> list[Package]:
    async with sessions() as session:
        query = select(Package).order_by(Package.uc_amount, Package.id)
        if active_only:
            query = query.where(Package.is_active.is_(True))
        return list((await session.scalars(query)).all())


async def get_package(
    sessions: async_sessionmaker[AsyncSession], package_id: int, active_only: bool = False
) -> Package | None:
    async with sessions() as session:
        package = await session.get(Package, package_id)
        if active_only and package is not None and not package.is_active:
            return None
        return package


async def add_package(
    sessions: async_sessionmaker[AsyncSession], name: str, uc_amount: int, price: Decimal
) -> Package:
    async with sessions.begin() as session:
        package = Package(name=name, uc_amount=uc_amount, price=price, is_active=True)
        session.add(package)
        await session.flush()
        await session.refresh(package)
        return package


async def update_package(
    sessions: async_sessionmaker[AsyncSession],
    package_id: int,
    *,
    name: str | None = None,
    uc_amount: int | None = None,
    price: Decimal | None = None,
    is_active: bool | None = None,
) -> bool:
    async with sessions.begin() as session:
        package = await session.get(Package, package_id)
        if package is None:
            return False
        if name is not None:
            package.name = name
        if uc_amount is not None:
            package.uc_amount = uc_amount
        if price is not None:
            package.price = price
        if is_active is not None:
            package.is_active = is_active
        return True


async def get_setting(sessions: async_sessionmaker[AsyncSession], key: str) -> str | None:
    async with sessions() as session:
        setting = await session.get(Setting, key)
        return setting.value if setting else None


async def set_setting(sessions: async_sessionmaker[AsyncSession], key: str, value: str) -> None:
    async with sessions.begin() as session:
        setting = await session.get(Setting, key)
        if setting is None:
            session.add(Setting(key=key, value=value))
        else:
            setting.value = value


async def create_order(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    package: Package,
    player_id: str,
    player_nickname: str,
    receipt_file_id: str,
    receipt_kind: str,
) -> Order:
    async with sessions.begin() as session:
        order = Order(
            user_id=user_id,
            package_id=package.id,
            package_name=package.name,
            uc_amount=package.uc_amount,
            price=package.price,
            player_id=player_id,
            player_nickname=player_nickname,
            receipt_file_id=receipt_file_id,
            receipt_kind=receipt_kind,
        )
        session.add(order)
        await session.flush()
        await session.refresh(order)
        return order


async def get_order(sessions: async_sessionmaker[AsyncSession], order_id: int) -> Order | None:
    async with sessions() as session:
        return await session.get(Order, order_id)


async def transition_order(
    sessions: async_sessionmaker[AsyncSession],
    order_id: int,
    *,
    expected_status: str,
    new_status: str,
    reviewer_id: int,
    reason: str | None = None,
) -> bool:
    if expected_status != "PENDING" or new_status not in {"APPROVED", "REJECTED"}:
        raise ValueError("Orders can only transition from PENDING to APPROVED or REJECTED.")
    if new_status == "REJECTED" and not (reason and reason.strip()):
        raise ValueError("A rejection reason is required.")
    values: dict[str, object] = {
        "status": new_status,
        "reviewed_by": reviewer_id,
        "reviewed_at": func.now(),
    }
    if reason is not None:
        values["rejection_reason"] = reason
    async with sessions.begin() as session:
        result = await session.execute(
            update(Order)
            .where(Order.id == order_id, Order.status == expected_status)
            .values(**values)
        )
        return result.rowcount == 1


async def set_fulfillment(
    sessions: async_sessionmaker[AsyncSession],
    order_id: int,
    status: str,
    detail: str,
) -> None:
    if status not in {"CONFIRMED", "SIMULATED", "FAILED"}:
        raise ValueError("Invalid fulfillment status.")
    async with sessions.begin() as session:
        await session.execute(
            update(Order).where(Order.id == order_id).values(
                fulfillment_status=status, fulfillment_detail=detail
            )
        )


async def list_user_orders(
    sessions: async_sessionmaker[AsyncSession], user_id: int, limit: int = 10
) -> list[Order]:
    async with sessions() as session:
        result = await session.scalars(
            select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(limit)
        )
        return list(result.all())


async def get_order_stats(sessions: async_sessionmaker[AsyncSession]) -> tuple[int, int, Decimal]:
    async with sessions() as session:
        total, pending, revenue = (
            await session.execute(
                select(
                    func.count(Order.id),
                    func.sum(case((Order.status == "PENDING", 1), else_=0)),
                    func.coalesce(
                        func.sum(case((Order.status == "APPROVED", Order.price), else_=0)),
                        0,
                    ),
                )
            )
        ).one()
        return int(total or 0), int(pending or 0), Decimal(str(revenue or 0))
