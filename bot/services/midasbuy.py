import logging
from dataclasses import dataclass

import aiohttp

from bot.config import Settings

logger = logging.getLogger(__name__)


class ProviderUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class FulfillmentResult:
    confirmed: bool
    simulated: bool
    detail: str
    transaction_id: str | None = None


class MidasbuyClient:
    def __init__(self, session: aiohttp.ClientSession, settings: Settings):
        self.session = session
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        if self.settings.midasbuy_api_token:
            return {"Authorization": f"Bearer {self.settings.midasbuy_api_token}"}
        return {}

    async def lookup_player(self, player_id: str) -> str:
        if self.settings.midasbuy_mode == "mock":
            return f"TEST_PLAYER_{player_id}"
        if self.settings.midasbuy_mode != "real" or not self.settings.midasbuy_lookup_url:
            raise ProviderUnavailable("Player lookup is not configured.")

        try:
            async with self.session.get(
                self.settings.midasbuy_lookup_url,
                params={"player_id": player_id},
                headers=self._headers(),
            ) as response:
                response.raise_for_status()
                payload = await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            logger.warning("Player lookup failed for player ID %s: %s", player_id, exc)
            raise ProviderUnavailable("Player lookup service could not be reached.") from exc

        nickname = payload.get("nickname") if isinstance(payload, dict) else None
        if not isinstance(nickname, str) or not nickname.strip():
            raise ProviderUnavailable("Player lookup response did not contain a nickname.")
        return nickname.strip()

    async def fulfill(
        self, *, order_id: int, player_id: str, uc_amount: int
    ) -> FulfillmentResult:
        if self.settings.midasbuy_mode == "mock":
            return FulfillmentResult(
                confirmed=False,
                simulated=True,
                detail="Mock mode is enabled; no UC was sent.",
            )
        if self.settings.midasbuy_mode != "real" or not self.settings.uc_fulfillment_url:
            return FulfillmentResult(
                confirmed=False,
                simulated=False,
                detail="UC fulfillment provider is not configured.",
            )

        try:
            async with self.session.post(
                self.settings.uc_fulfillment_url,
                json={"order_id": order_id, "player_id": player_id, "uc_amount": uc_amount},
                headers=self._headers(),
            ) as response:
                response.raise_for_status()
                payload = await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            logger.exception("UC fulfillment request failed for order %s", order_id)
            return FulfillmentResult(
                confirmed=False,
                simulated=False,
                detail=f"Provider request failed: {type(exc).__name__}.",
            )

        if not isinstance(payload, dict):
            return FulfillmentResult(False, False, "Provider returned an invalid response.")
        transaction_id = payload.get("transaction_id")
        if payload.get("success") is True and isinstance(transaction_id, str) and transaction_id.strip():
            return FulfillmentResult(
                confirmed=True,
                simulated=False,
                detail="Provider confirmed fulfillment.",
                transaction_id=transaction_id.strip(),
            )
        return FulfillmentResult(
            confirmed=False,
            simulated=False,
            detail="Provider did not confirm fulfillment.",
        )
