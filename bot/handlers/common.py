from aiogram.types import User as TelegramUser


def is_admin(user: TelegramUser, admin_ids: frozenset[int]) -> bool:
    return user.id in admin_ids
