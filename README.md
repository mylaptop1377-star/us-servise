# PUBG Mobile UC Telegram bot

Telegram bot for Uzbek-language PUBG Mobile UC orders, payment-receipt review, and admin package management. Python 3.11+, aiogram 3, SQLAlchemy async/SQLite, aiohttp, and in-memory FSM.

## Ishga tushirish / Setup

1. Python 3.11 yoki yangiroq versiyani o'rnating.
2. Virtual muhit yarating va `pip install -r requirements.txt` buyrug'ini bajaring.
3. `.env.example` faylidan `.env` nusxa oling. `BOT_TOKEN` ni BotFather tokeni, `ADMIN_IDS` ni esa vergul bilan ajratilgan Telegram raqamli ID'lari bilan to'ldiring. Tokenni hech qachon repozitoriyga joylamang.
4. `python main.py` bilan ishga tushiring. SQLite sxemasi avtomatik yaratiladi; birinchi ishga tushishda tahrirlash mumkin bo'lgan namunaviy paketlar qo'shiladi.
5. Botda `/admin` oching, `To'lov sozlamalari` orqali `/setcard` va `/setholder` buyruqlaridan foydalaning. Narxlar va paketlar `Paketlar` bo'limidan boshqariladi.

Start / run: configure `.env`, install `requirements.txt`, then run `python main.py`. The database defaults to `data/bot.db`; FSM state uses memory and resets on restart.

## Midasbuy and UC provider integration

The repository has no verified production Midasbuy credentials or provider contract. The safe default `MIDASBUY_MODE=disabled` does not perform player lookups, and UC fulfillment is not claimed unless a configured real provider explicitly confirms it.

- `disabled`: lookup asks the buyer to retry; an approved order records provider unavailability and tells the buyer delivery is unconfirmed.
- `mock`: lookup returns `TEST_PLAYER_<id>` for development. Approval records a simulation only; it **never sends or claims real UC**.
- `real`: configure both endpoint URLs and optionally `MIDASBUY_API_TOKEN`. Lookup uses `GET MIDASBUY_LOOKUP_URL?player_id=<id>` and expects JSON `{"nickname":"..."}`. Fulfillment uses `POST UC_FULFILLMENT_URL` with JSON `{"order_id":1,"player_id":"...","uc_amount":60}` and expects `{"success":true,"transaction_id":"..."}`. The bot only reports delivery confirmed for that explicit success response with a non-empty transaction ID. Adapt `bot/services/midasbuy.py` to the provider's documented API before production; these generic request shapes are not a verified Midasbuy API.

## Privacy and retention

Order records include Telegram user ID, player ID/nickname, package, status, and the Telegram file ID for the receipt. Receipts are not downloaded to this server; the bot sends the receipt to configured admins for review. Database records/file IDs remain until an operator removes them from the SQLite database and its backups. Restrict server/database access, use trusted admins, and define an appropriate retention/deletion process before launch.
