import logging
import re
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.database.requests import (
    create_order,
    get_package,
    get_setting,
    list_packages,
)
from bot.keyboards.inline import order_review, package_choices, player_confirmation
from bot.keyboards.reply import main_menu
from bot.services.midasbuy import MidasbuyClient, ProviderUnavailable
from bot.states.order_states import PurchaseStates

logger = logging.getLogger(__name__)
router = Router(name="uc_order")


@router.message(F.text == "🛒 UC sotib olish")
async def begin_purchase(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(PurchaseStates.waiting_player_id)
    await message.answer("PUBG Mobile o'yinchi ID raqamingizni yuboring (faqat raqamlar).")


@router.message(Command("cancel"))
async def cancel_purchase(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Amal bekor qilindi.", reply_markup=main_menu())


@router.message(PurchaseStates.waiting_player_id)
async def receive_player_id(
    message: Message,
    state: FSMContext,
    midasbuy: MidasbuyClient,
) -> None:
    player_id = (message.text or "").strip()
    if not re.fullmatch(r"\d{1,20}", player_id):
        await message.answer("ID faqat 1–20 ta raqamdan iborat bo'lishi kerak. Qayta yuboring.")
        return
    try:
        nickname = await midasbuy.lookup_player(player_id)
    except ProviderUnavailable as exc:
        await message.answer(
            f"O'yinchi ma'lumotini tekshirib bo'lmadi: {escape(str(exc))}\n"
            "Birozdan so'ng qayta urinib ko'ring."
        )
        return

    await state.update_data(player_id=player_id, player_nickname=nickname)
    await state.set_state(PurchaseStates.confirming_player)
    await message.answer(
        f"O'yinchi: <b>{escape(nickname)}</b>\nID: <code>{escape(player_id)}</code>\n"
        "Shu akkaunt ekanini tasdiqlaysizmi?",
        reply_markup=player_confirmation(),
    )


@router.callback_query(PurchaseStates.confirming_player, F.data == "player:retry")
async def retry_player_id(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PurchaseStates.waiting_player_id)
    await callback.answer()
    if callback.message:
        await callback.message.answer("O'yinchi ID raqamingizni qayta yuboring.")


@router.callback_query(PurchaseStates.confirming_player, F.data == "player:confirm")
async def confirm_player(
    callback: CallbackQuery,
    state: FSMContext,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    packages = await list_packages(sessions)
    if not packages:
        await callback.answer("Hozir faol paketlar mavjud emas.", show_alert=True)
        return
    await state.set_state(PurchaseStates.choosing_package)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Kerakli UC paketini tanlang:",
            reply_markup=package_choices(packages),
        )


@router.callback_query(PurchaseStates.choosing_package, F.data.startswith("pkg:"))
async def choose_package(
    callback: CallbackQuery,
    state: FSMContext,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        package_id = int((callback.data or "").split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Paket tanlovi noto'g'ri.", show_alert=True)
        return
    package = await get_package(sessions, package_id, active_only=True)
    if package is None:
        await callback.answer("Bu paket endi faol emas.", show_alert=True)
        return

    await state.update_data(package_id=package.id)
    await state.set_state(PurchaseStates.waiting_receipt)
    card = await get_setting(sessions, "payment_card")
    holder = await get_setting(sessions, "payment_holder")
    payment = (
        f"Karta: <code>{escape(card)}</code>\nKarta egasi: {escape(holder or 'Koʻrsatilmagan')}"
        if card
        else "To'lov rekvizitlari hali sozlanmagan. To'lov qilishdan oldin admin bilan bog'laning."
    )
    await callback.answer()
    await callback.message.answer(
        f"<b>{escape(package.name)}</b> — {package.uc_amount} UC, "
        f"{package.price:,.0f} so'm\n\n{payment}\n\n"
        "To'lovdan keyin chek rasmini yoki PDF faylini yuboring."
    )


@router.message(PurchaseStates.waiting_receipt)
async def receive_receipt(
    message: Message,
    state: FSMContext,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    file_id: str | None = None
    kind: str | None = None
    if message.photo:
        file_id, kind = message.photo[-1].file_id, "photo"
    elif message.document and (
        message.document.mime_type == "application/pdf"
        or (message.document.file_name or "").lower().endswith(".pdf")
    ):
        file_id, kind = message.document.file_id, "document"

    if file_id is None or kind is None:
        await message.answer("Chekni rasm yoki PDF fayl ko'rinishida yuboring.")
        return

    data = await state.get_data()
    package_id = data.get("package_id")
    player_id = data.get("player_id")
    nickname = data.get("player_nickname")
    if not isinstance(package_id, int) or not isinstance(player_id, str) or not isinstance(nickname, str):
        await state.clear()
        await message.answer("Buyurtma ma'lumotlari eskirgan. Iltimos, qaytadan boshlang.")
        return
    package = await get_package(sessions, package_id, active_only=True)
    if package is None:
        await state.clear()
        await message.answer("Tanlangan paket endi faol emas. Iltimos, qaytadan boshlang.")
        return

    order = await create_order(
        sessions,
        user_id=message.from_user.id,
        package=package,
        player_id=player_id,
        player_nickname=nickname,
        receipt_file_id=file_id,
        receipt_kind=kind,
    )
    await state.clear()
    await message.answer(
        f"✅ Chek qabul qilindi. Buyurtma <b>#{order.id}</b> admin tomonidan tekshiriladi.",
        reply_markup=main_menu(),
    )

    username = f"@{escape(message.from_user.username)}" if message.from_user.username else "username yo'q"
    caption = (
        f"🧾 <b>Yangi buyurtma #{order.id}</b>\n"
        f"Foydalanuvchi: {escape(message.from_user.full_name)} ({username})\n"
        f"Telegram ID: <code>{message.from_user.id}</code>\n"
        f"O'yinchi: <b>{escape(nickname)}</b> (<code>{escape(player_id)}</code>)\n"
        f"Paket: {escape(package.name)} — {package.uc_amount} UC\n"
        f"To'lov: {package.price:,.0f} so'm\nHolat: PENDING"
    )
    notified = False
    for admin_id in settings.admin_ids:
        try:
            if kind == "photo":
                await message.bot.send_photo(
                    admin_id,
                    file_id,
                    caption=caption,
                    reply_markup=order_review(order.id),
                )
            else:
                await message.bot.send_document(
                    admin_id,
                    file_id,
                    caption=caption,
                    reply_markup=order_review(order.id),
                )
            notified = True
        except TelegramAPIError:
            logger.exception("Failed to send order %s receipt to admin %s", order.id, admin_id)
    if not settings.admin_ids or not notified:
        logger.error("Order %s is saved but could not be delivered to any configured admin", order.id)
