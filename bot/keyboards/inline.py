from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.models import Package


def player_confirmation() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="player:confirm"),
                InlineKeyboardButton(text="🔁 Qayta kiritish", callback_data="player:retry"),
            ]
        ]
    )


def package_choices(packages: list[Package]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        f"{package.name[:26]} — {package.uc_amount} UC, "
                        f"{package.price:,.0f} so'm"
                    ),
                    callback_data=f"pkg:{package.id}",
                )
            ]
            for package in packages
        ]
    )


def admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Paketlar", callback_data="admin:packages")],
            [InlineKeyboardButton(text="💳 To'lov sozlamalari", callback_data="admin:payment")],
            [InlineKeyboardButton(text="📊 Statistika", callback_data="admin:stats")],
            [InlineKeyboardButton(text="📣 Xabar yuborish", callback_data="admin:broadcast")],
        ]
    )


def package_admin_menu(packages: list[Package]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"{'🟢' if package.is_active else '⚫'} {package.name[:32]} "
                    f"({package.uc_amount} UC)"
                ),
                callback_data=f"admin:pkg:{package.id}",
            )
        ]
        for package in packages
    ]
    rows.append([InlineKeyboardButton(text="➕ Yangi paket", callback_data="admin:pkg:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def package_edit_menu(package: Package) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Nomi", callback_data=f"admin:edit:{package.id}:name")],
            [InlineKeyboardButton(text="UC miqdori", callback_data=f"admin:edit:{package.id}:uc")],
            [InlineKeyboardButton(text="Narxi", callback_data=f"admin:edit:{package.id}:price")],
            [
                InlineKeyboardButton(
                    text="Faolsizlantirish" if package.is_active else "Faollashtirish",
                    callback_data=f"admin:toggle:{package.id}",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Paketlar", callback_data="admin:packages")],
        ]
    )


def order_review(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"order:approve:{order_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"order:reject:{order_id}"),
            ]
        ]
    )
