from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.database.requests import list_user_orders, upsert_user
from bot.keyboards.reply import main_menu

router = Router(name="start")

HELP_TEXT = (
    "🛒 <b>UC sotib olish</b> tugmasini bosing va o'yinchi ID raqamingizni kiriting.\n"
    "Nick tasdiqlangach, paket tanlang, to'lov qiling va chek rasmini yoki PDF faylini yuboring.\n"
    "Buyurtma admin tekshiruvidan so'ng ko'rib chiqiladi. Provider tasdiqlamaguncha UC "
    "yetkazib berildi deb ko'rsatilmaydi."
)


@router.message(CommandStart())
async def start(
    message: Message,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None:
        return
    await upsert_user(
        sessions,
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )
    await message.answer(
        f"Assalomu alaykum, {escape(message.from_user.full_name)}! PUBG Mobile UC botiga xush kelibsiz.",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
@router.message(lambda message: message.text == "ℹ️ Yordam")
async def help_message(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu())


@router.message(lambda message: message.text == "👤 Profil")
async def profile(
    message: Message,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None:
        return
    await upsert_user(
        sessions,
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )
    orders = await list_user_orders(sessions, message.from_user.id, limit=5)
    latest = f"\nSo'nggi buyurtmalar: {len(orders)} ta" if orders else "\nHozircha buyurtmalar yo'q."
    await message.answer(
        f"👤 <b>Profil</b>\nIsm: {escape(message.from_user.full_name)}\n"
        f"Telegram ID: <code>{message.from_user.id}</code>{latest}",
        reply_markup=main_menu(),
    )


@router.message(lambda message: message.text == "📜 Buyurtmalarim")
async def order_history(
    message: Message,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None:
        return
    orders = await list_user_orders(sessions, message.from_user.id)
    if not orders:
        await message.answer("Buyurtmalar tarixi bo'sh.", reply_markup=main_menu())
        return

    status_text = {
        "PENDING": "Ko'rib chiqilmoqda",
        "APPROVED": "To'lov tasdiqlangan",
        "REJECTED": "Rad etilgan",
    }
    lines = ["📜 <b>So'nggi buyurtmalar</b>"]
    for order in orders:
        lines.append(
            f"#{order.id} — {order.uc_amount} UC, {order.price:,.0f} so'm — "
            f"{status_text.get(order.status, 'Noma’lum')}"
        )
        if order.status == "APPROVED" and order.fulfillment_status != "CONFIRMED":
            lines.append("  UC yetkazilishi provider tomonidan hali tasdiqlanmagan.")
    await message.answer("\n".join(lines), reply_markup=main_menu())
