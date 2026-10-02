import asyncio
import logging
from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.database.requests import (
    add_package,
    get_order,
    get_package,
    get_order_stats,
    get_setting,
    list_packages,
    set_fulfillment,
    set_setting,
    transition_order,
    update_package,
)
from bot.handlers.common import is_admin
from bot.keyboards.inline import admin_panel, package_admin_menu, package_edit_menu
from bot.services.midasbuy import FulfillmentResult, MidasbuyClient
from bot.states.order_states import AdminStates

logger = logging.getLogger(__name__)
router = Router(name="admin")


def _admin(callback: CallbackQuery, settings: Settings) -> bool:
    return callback.from_user is not None and is_admin(callback.from_user, settings.admin_ids)


@router.message(Command("admin"))
async def admin_command(message: Message, settings: Settings, state: FSMContext) -> None:
    if (
        message.chat.type != "private"
        or message.from_user is None
        or not is_admin(message.from_user, settings.admin_ids)
    ):
        await message.answer("⛔ Admin paneli faqat adminning shaxsiy chatida ishlaydi.")
        return
    await state.clear()
    await message.answer("🔧 <b>Admin panel</b>", reply_markup=admin_panel())


@router.message(Command("cancel"))
async def cancel_admin_action(message: Message, settings: Settings, state: FSMContext) -> None:
    if (
        message.chat.type == "private"
        and message.from_user is not None
        and is_admin(message.from_user, settings.admin_ids)
    ):
        await state.clear()
        await message.answer("Amal bekor qilindi.")


@router.callback_query(F.data.startswith("admin:"))
async def admin_actions(
    callback: CallbackQuery,
    state: FSMContext,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if (
        callback.message is None
        or callback.message.chat.type != "private"
        or not _admin(callback, settings)
    ):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    if action == "packages":
        packages = await list_packages(sessions, active_only=False)
        await callback.message.answer(
            "📦 Paketni tahrirlash yoki yangi paket qo'shish:",
            reply_markup=package_admin_menu(packages),
        )
    elif action == "pkg" and len(parts) == 3 and parts[2] == "add":
        await state.clear()
        await state.set_state(AdminStates.adding_package_name)
        await callback.message.answer("Yangi paket nomini yuboring:")
    elif action == "pkg" and len(parts) == 3:
        package = await _package_from_id(sessions, parts[2])
        if package is None:
            await callback.answer("Paket topilmadi.", show_alert=True)
            return
        await callback.message.answer(
            f"<b>{escape(package.name)}</b> — {package.uc_amount} UC, "
            f"{package.price:,.0f} so'm; holati: {'faol' if package.is_active else 'faol emas'}",
            reply_markup=package_edit_menu(package),
        )
    elif action == "edit" and len(parts) == 4:
        package = await _package_from_id(sessions, parts[2])
        field = parts[3]
        if package is None or field not in {"name", "uc", "price"}:
            await callback.answer("Paket yoki maydon noto'g'ri.", show_alert=True)
            return
        await state.update_data(package_id=package.id, edit_field=field)
        await state.set_state(AdminStates.editing_package_value)
        prompt = {
            "name": "Yangi paket nomini yuboring:",
            "uc": "Yangi UC miqdorini yuboring (butun son):",
            "price": "Yangi narxni yuboring (so'm, raqam):",
        }[field]
        await callback.message.answer(prompt)
    elif action == "toggle" and len(parts) == 3:
        package = await _package_from_id(sessions, parts[2])
        if package is None:
            await callback.answer("Paket topilmadi.", show_alert=True)
            return
        await update_package(sessions, package.id, is_active=not package.is_active)
        await callback.answer("Paket holati yangilandi.")
        await callback.message.answer("📦 Paketlar:", reply_markup=package_admin_menu(
            await list_packages(sessions, active_only=False)
        ))
        return
    elif action == "payment":
        card = await get_setting(sessions, "payment_card")
        holder = await get_setting(sessions, "payment_holder")
        await callback.message.answer(
            f"Karta: {escape(card or 'sozlanmagan')}\n"
            f"Karta egasi: {escape(holder or 'sozlanmagan')}\n\n"
            "Rekvizitni o'zgartirish uchun yuboring:\n"
            "/setcard <raqam>\n/setholder <ism>"
        )
    elif action == "stats":
        total, pending, revenue = await get_order_stats(sessions)
        await callback.message.answer(
            f"📊 <b>Buyurtmalar statistikasi</b>\nJami buyurtma: {total}\n"
            f"Kutilayotgan: {pending}\nTasdiqlangan to'lovlar bo'yicha tushum: {revenue:,.0f} so'm"
        )
    elif action == "broadcast":
        await state.clear()
        await state.set_state(AdminStates.broadcasting)
        await callback.message.answer("Barcha foydalanuvchilarga yuboriladigan matnni kiriting.")
    else:
        await callback.answer("Noma'lum admin amali.", show_alert=True)
        return
    await callback.answer()


async def _package_from_id(
    sessions: async_sessionmaker[AsyncSession], raw_id: str
):
    try:
        package_id = int(raw_id)
    except ValueError:
        return None
    return await get_package(sessions, package_id)


@router.message(Command("setcard"))
async def set_card(
    message: Message,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if (
        message.chat.type != "private"
        or message.from_user is None
        or not is_admin(message.from_user, settings.admin_ids)
    ):
        await message.answer("⛔ Bu buyruq faqat adminning shaxsiy chatida ishlaydi.")
        return
    value = (message.text or "").partition(" ")[2].strip()
    if not value or len(value) > 100:
        await message.answer("Foydalanish: /setcard <karta raqami>")
        return
    await set_setting(sessions, "payment_card", value)
    await message.answer("✅ Karta rekviziti saqlandi.")


@router.message(Command("setholder"))
async def set_holder(
    message: Message,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if (
        message.chat.type != "private"
        or message.from_user is None
        or not is_admin(message.from_user, settings.admin_ids)
    ):
        await message.answer("⛔ Bu buyruq faqat adminning shaxsiy chatida ishlaydi.")
        return
    value = (message.text or "").partition(" ")[2].strip()
    if not value or len(value) > 200:
        await message.answer("Foydalanish: /setholder <karta egasining ismi>")
        return
    await set_setting(sessions, "payment_holder", value)
    await message.answer("✅ Karta egasi saqlandi.")


@router.message(AdminStates.adding_package_name)
async def receive_package_name(message: Message, state: FSMContext, settings: Settings) -> None:
    if message.from_user is None or not is_admin(message.from_user, settings.admin_ids):
        await state.clear()
        return
    name = (message.text or "").strip()
    if not name or len(name) > 100:
        await message.answer("Nom 1–100 belgi bo'lishi kerak. Qayta kiriting:")
        return
    await state.update_data(package_name=name)
    await state.set_state(AdminStates.adding_package_uc)
    await message.answer("Paketdagi UC miqdorini yuboring (musbat butun son):")


@router.message(AdminStates.adding_package_uc)
async def receive_package_uc(message: Message, state: FSMContext, settings: Settings) -> None:
    if message.from_user is None or not is_admin(message.from_user, settings.admin_ids):
        await state.clear()
        return
    try:
        amount = int((message.text or "").strip())
        if not 1 <= amount <= 10_000_000:
            raise ValueError
    except ValueError:
        await message.answer("UC miqdori 1–10 000 000 orasidagi butun son bo'lishi kerak:")
        return
    await state.update_data(package_uc=amount)
    await state.set_state(AdminStates.adding_package_price)
    await message.answer("Paket narxini so'mda yuboring (musbat son):")


@router.message(AdminStates.adding_package_price)
async def receive_package_price(
    message: Message,
    state: FSMContext,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None or not is_admin(message.from_user, settings.admin_ids):
        await state.clear()
        return
    try:
        price = Decimal((message.text or "").strip().replace(",", ""))
        if not price.is_finite() or price <= 0 or price > Decimal("9999999999"):
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("Narx 0 dan katta va 10 milliard so'mdan kam bo'lishi kerak:")
        return
    data = await state.get_data()
    package = await add_package(sessions, data["package_name"], data["package_uc"], price)
    await state.clear()
    await message.answer(
        f"✅ {escape(package.name)} — {package.uc_amount} UC, {package.price:,.0f} so'm qo'shildi."
    )


@router.message(AdminStates.editing_package_value)
async def receive_package_edit(
    message: Message,
    state: FSMContext,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None or not is_admin(message.from_user, settings.admin_ids):
        await state.clear()
        return
    data = await state.get_data()
    field = data.get("edit_field")
    package_id = data.get("package_id")
    raw_value = (message.text or "").strip()
    try:
        if field == "name" and raw_value and len(raw_value) <= 100:
            updated = await update_package(sessions, package_id, name=raw_value)
        elif field == "uc":
            amount = int(raw_value)
            if not 1 <= amount <= 10_000_000:
                raise ValueError
            updated = await update_package(sessions, package_id, uc_amount=amount)
        elif field == "price":
            price = Decimal(raw_value.replace(",", ""))
            if not price.is_finite() or price <= 0 or price > Decimal("9999999999"):
                raise InvalidOperation
            updated = await update_package(sessions, package_id, price=price)
        else:
            raise ValueError
    except (ValueError, InvalidOperation):
        await message.answer("Qiymat noto'g'ri. To'g'ri qiymat yuboring yoki /cancel bilan bekor qiling.")
        return
    await state.clear()
    await message.answer("✅ Paket yangilandi." if updated else "Paket topilmadi.")


@router.message(AdminStates.rejecting_order)
async def receive_rejection_reason(
    message: Message,
    state: FSMContext,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None or not is_admin(message.from_user, settings.admin_ids):
        await state.clear()
        return
    reason = (message.text or "").strip()
    if not reason or len(reason) > 1000:
        await message.answer("Sabab 1–1000 belgi bo'lishi kerak. Qayta kiriting:")
        return
    data = await state.get_data()
    order_id = data.get("reject_order_id")
    if not isinstance(order_id, int):
        await state.clear()
        await message.answer("Buyurtma ma'lumoti eskirgan.")
        return
    order = await get_order(sessions, order_id)
    if order is None or order.status != "PENDING":
        await state.clear()
        await message.answer("Buyurtma topilmadi yoki allaqachon ko'rib chiqilgan.")
        return
    changed = await transition_order(
        sessions,
        order_id,
        expected_status="PENDING",
        new_status="REJECTED",
        reviewer_id=message.from_user.id,
        reason=reason,
    )
    await state.clear()
    if not changed:
        await message.answer("Boshqa admin buyurtmani oldin ko'rib chiqqan.")
        return
    review_chat_id = data.get("review_chat_id")
    review_message_id = data.get("review_message_id")
    if isinstance(review_chat_id, int) and isinstance(review_message_id, int):
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=review_chat_id,
                message_id=review_message_id,
                reply_markup=None,
            )
        except TelegramAPIError:
            logger.debug("Could not remove rejected order %s review buttons", order_id, exc_info=True)
    await _notify_user(
        message, order.user_id,
        f"❌ <b>#{order.id}</b> buyurtmangiz rad etildi.\nSabab: {escape(reason)}",
    )
    await message.answer(f"Buyurtma #{order.id} rad etildi.")


@router.callback_query(F.data.startswith("order:"))
async def review_order(
    callback: CallbackQuery,
    state: FSMContext,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    midasbuy: MidasbuyClient,
) -> None:
    if (
        callback.message is None
        or callback.message.chat.type != "private"
        or not _admin(callback, settings)
    ):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("So'rov noto'g'ri.", show_alert=True)
        return
    try:
        order_id = int(parts[2])
    except ValueError:
        await callback.answer("Buyurtma raqami noto'g'ri.", show_alert=True)
        return
    order = await get_order(sessions, order_id)
    if order is None:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return

    if parts[1] == "reject":
        if order.status != "PENDING":
            await callback.answer("Buyurtma allaqachon ko'rib chiqilgan.", show_alert=True)
            return
        await state.clear()
        await state.update_data(
            reject_order_id=order_id,
            review_chat_id=callback.message.chat.id,
            review_message_id=callback.message.message_id,
        )
        await state.set_state(AdminStates.rejecting_order)
        await callback.answer()
        await callback.message.answer(f"#{order_id} buyurtmani rad etish sababini yuboring.")
        return
    if parts[1] != "approve":
        await callback.answer("Noma'lum amal.", show_alert=True)
        return

    changed = await transition_order(
        sessions,
        order_id,
        expected_status="PENDING",
        new_status="APPROVED",
        reviewer_id=callback.from_user.id,
    )
    if not changed:
        await callback.answer("Buyurtma allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    await callback.answer("To'lov tasdiqlandi; provider holati tekshirilmoqda.")

    try:
        result = await midasbuy.fulfill(
            order_id=order.id, player_id=order.player_id, uc_amount=order.uc_amount
        )
    except Exception as exc:
        logger.exception("Unexpected fulfillment error for order %s", order.id)
        result = FulfillmentResult(
            confirmed=False, simulated=False, detail=f"Unexpected error: {type(exc).__name__}."
        )

    if result.confirmed and not result.simulated:
        await set_fulfillment(
            sessions, order.id, "CONFIRMED", f"{result.detail} Transaction: {result.transaction_id}"
        )
        user_text = (
            f"✅ To'lov va UC yetkazilishi tasdiqlandi. Buyurtma <b>#{order.id}</b>.\n"
            f"Tranzaksiya: <code>{escape(result.transaction_id or '')}</code>"
        )
        admin_text = f"Provider UC yetkazilishini tasdiqladi: {escape(result.transaction_id or '')}."
    elif result.simulated:
        await set_fulfillment(sessions, order.id, "SIMULATED", result.detail)
        user_text = (
            f"✅ To'lov qabul qilindi. Buyurtma <b>#{order.id}</b> tasdiqlandi, ammo "
            "TEST rejimida haqiqiy UC yuborilmadi. UC yetkazilishi tasdiqlanmagan."
        )
        admin_text = "TEST rejimi: UC yuborilmadi va haqiqiy yetkazilish tasdiqlanmadi."
    else:
        await set_fulfillment(sessions, order.id, "FAILED", result.detail)
        user_text = (
            f"✅ To'lov qabul qilindi. Buyurtma <b>#{order.id}</b> tasdiqlandi, lekin "
            "UC yetkazilishi hali tasdiqlanmadi. Admin muammoni tekshiradi."
        )
        admin_text = f"⚠️ UC yetkazilmadi/tasdiqlanmadi: {escape(result.detail)}"
    await _notify_user(callback.message, order.user_id, user_text)
    await callback.message.answer(f"#{order.id}: {admin_text}")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError:
        logger.debug("Could not remove order %s review buttons", order.id, exc_info=True)


async def _notify_user(message: Message, user_id: int, text: str) -> None:
    try:
        await message.bot.send_message(user_id, text)
    except TelegramAPIError:
        logger.warning("Could not notify user %s about order update", user_id, exc_info=True)


@router.message(AdminStates.broadcasting)
async def broadcast(
    message: Message,
    state: FSMContext,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None or not is_admin(message.from_user, settings.admin_ids):
        await state.clear()
        return
    text = (message.text or "").strip()
    if text == "/cancel":
        await state.clear()
        await message.answer("Xabar yuborish bekor qilindi.")
        return
    if not text:
        await message.answer("Matnli xabar yuboring yoki /cancel bilan bekor qiling.")
        return
    from sqlalchemy import select
    from bot.database.models import User

    async with sessions() as session:
        user_ids = list((await session.scalars(select(User.id))).all())
    sent = failed = 0
    for user_id in user_ids:
        try:
            await message.bot.send_message(user_id, text, parse_mode=None)
            sent += 1
        except TelegramAPIError:
            failed += 1
            logger.info("Broadcast delivery failed for user %s", user_id, exc_info=True)
        await asyncio.sleep(0.04)
    await state.clear()
    await message.answer(f"📣 Xabar yakunlandi. Yuborildi: {sent}, xatolik: {failed}.")
