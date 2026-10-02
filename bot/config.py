from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    database_url: str
    midasbuy_mode: str
    midasbuy_lookup_url: str | None
    uc_fulfillment_url: str | None
    midasbuy_api_token: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        admins: set[int] = set()
        for value in os.getenv("ADMIN_IDS", "").split(","):
            value = value.strip()
            if value:
                try:
                    admins.add(int(value))
                except ValueError as exc:
                    raise ValueError(f"ADMIN_IDS contains an invalid Telegram ID: {value!r}") from exc

        mode = os.getenv("MIDASBUY_MODE", "disabled").strip().lower()
        if mode not in {"disabled", "mock", "real"}:
            raise ValueError("MIDASBUY_MODE must be one of: disabled, mock, real")

        return cls(
            bot_token=os.getenv("BOT_TOKEN", "").strip(),
            admin_ids=frozenset(admins),
            database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db"),
            midasbuy_mode=mode,
            midasbuy_lookup_url=os.getenv("MIDASBUY_LOOKUP_URL", "").strip() or None,
            uc_fulfillment_url=os.getenv("UC_FULFILLMENT_URL", "").strip() or None,
            midasbuy_api_token=os.getenv("MIDASBUY_API_TOKEN", "").strip() or None,
        )
