"""Reading a business card: photos of its sides in, the fields printed on it out.

The reading is done by Claude's vision model through the Anthropic API. OCR
alone would hand back a column of text and leave the hard part — which line is
the person, which the company, which number the switchboard — to a pile of
heuristics; the model answers that directly, into a fixed schema.

Nothing here writes to the database. A reading is a draft the operator checks
and corrects before anything is filed (app/routers/business_cards.py), because
a misread digit in a phone number is not something to find out about later.

The photos go to Anthropic and nowhere else: they are not stored, and neither
they nor the reading appear in a log line.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Literal, Protocol

import anthropic
import httpx2
from pydantic import BaseModel, Field, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)

ImageType = Literal["image/jpeg", "image/png", "image/gif", "image/webp"]

# The API's own ceiling for one image. The client scales photos down before
# sending them, so a real card never comes near it.
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# Long enough for a slow vision request, short enough that the scan screen
# gives up rather than spins.
READ_TIMEOUT_SECONDS = 60

# Routes a declined request to another model instead of failing it outright.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class CardImage:
    data: bytes
    media_type: ImageType


def sniff_image_type(data: bytes) -> ImageType | None:
    """The image format from its first bytes, or None for anything else.

    The upload's declared content type is whatever the browser guessed; the
    model is only sent what it can actually decode.
    """
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class CardReading(BaseModel):
    """What the model reads off the card. Every field is optional: a card
    without a street address is normal, and a guess would be worse than a gap.

    The descriptions are the model's instructions for each field."""

    name: str | None = Field(None, description="The person's full name, as printed.")
    job_title: str | None = Field(None, description="The person's role or title.")
    email: str | None = Field(None, description="The person's own email address.")
    email_secondary: str | None = Field(None, description="A second personal email, if any.")
    phone: str | None = Field(
        None, description="The person's direct or mobile number, in international format."
    )
    phone_secondary: str | None = Field(
        None, description="A second personal number, in international format."
    )
    website: str | None = Field(None, description="The website printed on the card, as a URL.")
    street: str | None = Field(None, description="Street and house number.")
    postal_code: str | None = None
    city: str | None = None
    country: str | None = Field(
        None,
        description="ISO 3166-1 alpha-2 code, e.g. AT. Infer it from the address or the "
        "phone prefix only when unambiguous.",
    )
    organization_name: str | None = Field(None, description="The company's name.")
    organization_domain: str | None = Field(
        None, description="The company's domain without scheme or www, e.g. acme.example."
    )
    organization_email: str | None = Field(
        None, description="A shared company address such as office@ or info@."
    )
    organization_phone: str | None = Field(
        None, description="The company's switchboard number, in international format."
    )
    notes: str | None = Field(
        None,
        description="Anything else printed on the card worth keeping: VAT or registration "
        "numbers, social profiles, a second office. Not slogans.",
    )


SYSTEM_PROMPT = """\
You read business cards for a small CRM. You are given photos of the sides of \
one card and return what is printed on it, field by field.

Copy names, titles and addresses exactly as printed, keeping their language and \
accents. Write phone numbers in international format (+43 1 234 5678) when the \
country is clear. Keep a person's own email and number apart from the company's \
shared ones (office@, info@, a switchboard). Leave a field empty when the card \
does not show it; never invent or complete a value. If the photos do not show a \
business card, leave every field empty."""


class CardReadError(RuntimeError):
    """The card could not be read. The text is safe to show the operator."""


class CardReader(Protocol):
    async def read(self, images: list[CardImage]) -> CardReading:
        """Read one card from the photos of its sides, or raise CardReadError."""


class ClaudeCardReader:
    def __init__(
        self,
        api_key: str,
        model: str,
        # Injected by the tests; production talks to the network.
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=READ_TIMEOUT_SECONDS,
            max_retries=1,
            http_client=http_client,
        )
        self._model = model

    async def read(self, images: list[CardImage]) -> CardReading:
        content: list[anthropic.types.beta.BetaContentBlockParam] = []
        for side, image in zip(("Front", "Back"), images, strict=False):
            content.append({"type": "text", "text": f"{side} of the card:"})
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image.media_type,
                        "data": base64.standard_b64encode(image.data).decode("ascii"),
                    },
                }
            )
        content.append({"type": "text", "text": "Read this business card."})

        try:
            response = await self._client.beta.messages.parse(
                model=self._model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
                output_format=CardReading,
                # Transcription, not reasoning: the low end is plenty, and the
                # operator is waiting on the answer.
                output_config={"effort": "low"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.APIConnectionError:
            raise CardReadError("Could not reach the card reader — try again.") from None
        except anthropic.RateLimitError:
            raise CardReadError("The card reader is busy — try again in a minute.") from None
        except anthropic.APIStatusError as exc:
            # The status and request id are enough to look the call up; the
            # body could echo the request, and that holds the photos.
            logger.error(
                "Business card read failed: HTTP %s, request %s",
                exc.status_code,
                exc.request_id,
            )
            raise CardReadError("The card reader refused the request.") from None
        except ValidationError:
            # A refusal or a cut-off answer is not the JSON the schema asks
            # for, and the SDK's parser gives up on it before returning.
            raise CardReadError("The card reader gave no usable answer — try again.") from None

        if response.stop_reason == "refusal":
            raise CardReadError("The card reader declined to read these photos.")
        reading = response.parsed_output
        if reading is None:
            raise CardReadError("The card reader gave no usable answer — try again.")
        return reading


def get_card_reader() -> CardReader | None:
    """The configured reader, or None when no API key is set.

    A FastAPI dependency, so the tests swap in a fake with
    app.dependency_overrides.
    """
    if not settings.anthropic_api_key:
        return None
    return ClaudeCardReader(settings.anthropic_api_key, settings.business_card_model)
