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
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

import anthropic
import httpx2
from pydantic import BaseModel, ConfigDict, Field, ValidationError

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

    The model is asked for this as JSON and the answer is checked here, not
    by the API's structured output: with this many optional fields the API
    never finished preparing the format, and every read timed out (#262).

    The descriptions are the model's instructions for each field."""

    # A postcode or phone number may come back as a JSON number.
    model_config = ConfigDict(coerce_numbers_to_str=True)

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


def _answer_format() -> str:
    """The JSON the model is asked for, one line per field with what goes in it."""
    lines = [
        f'- "{name}": {field.description or name.replace("_", " ")}'
        for name, field in CardReading.model_fields.items()
    ]
    return (
        "Answer with one JSON object and nothing else — no prose, no code fence. "
        "Use these keys, with null for anything the card does not show:\n" + "\n".join(lines)
    )


INSTRUCTIONS = f"{SYSTEM_PROMPT}\n\n{_answer_format()}"


def parse_reading(text: str) -> CardReading:
    """The model's answer as a CardReading. Tolerates a code fence or a word
    around the object; raises ValidationError for anything that is not one."""
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]
    return CardReading.model_validate_json(text)


class CardReadError(RuntimeError):
    """The card could not be read. The text is safe to show the operator."""


class CardReadUsage(BaseModel):
    """What one read cost: the model that answered and the tokens it billed.

    Shown on the review screen so the cost of a scan can be checked against
    the price list without opening the Anthropic console.
    """

    # The model that actually answered — after a refusal fallback, not the one
    # asked for.
    model: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class CardRead:
    reading: CardReading
    usage: CardReadUsage


class CardReader(Protocol):
    async def read(self, images: list[CardImage]) -> CardRead:
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

    async def aclose(self) -> None:
        """Close the client's connection pool."""
        await self._client.close()

    async def read(self, images: list[CardImage]) -> CardRead:
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
            response = await self._client.beta.messages.create(
                model=self._model,
                max_tokens=4096,
                system=INSTRUCTIONS,
                messages=[{"role": "user", "content": content}],
                # Transcription, not reasoning: the low end is plenty, and the
                # operator is waiting on the answer.
                output_config={"effort": "low"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        # Every failure is logged before it becomes a 502: the SDK has already
        # retried once by then, and its own retry line is all a log would
        # otherwise show. Only the error is logged, never the request — that
        # holds the photos.
        except anthropic.APITimeoutError:
            logger.error("Business card read timed out after %ss", READ_TIMEOUT_SECONDS)
            raise CardReadError("The card reader took too long — try again.") from None
        except anthropic.APIConnectionError as exc:
            logger.error("Business card read could not connect: %r", exc.__cause__ or exc)
            raise CardReadError("Could not reach the card reader — try again.") from None
        except anthropic.APIStatusError as exc:
            logger.error(
                "Business card read failed: HTTP %s %s, request %s",
                exc.status_code,
                _api_error(exc),
                exc.request_id,
            )
            if isinstance(exc, anthropic.RateLimitError):
                raise CardReadError("The card reader is busy — try again in a minute.") from None
            raise CardReadError("The card reader refused the request.") from None

        if response.stop_reason == "refusal":
            logger.error("Business card read declined by %s", response.model)
            raise CardReadError("The card reader declined to read these photos.")
        text = "".join(block.text for block in response.content if block.type == "text")
        try:
            reading = parse_reading(text)
        except ValidationError:
            # Cut off at max_tokens, or not the JSON asked for. Neither the
            # answer nor its errors are logged: both hold what the card says.
            logger.error(
                "Business card read gave no usable answer: stop %s, %d characters",
                response.stop_reason,
                len(text),
            )
            raise CardReadError("The card reader gave no usable answer — try again.") from None
        usage = CardReadUsage(
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        logger.info(
            "Business card read by %s: %d input, %d output tokens",
            usage.model,
            usage.input_tokens,
            usage.output_tokens,
        )
        return CardRead(reading, usage)


def _api_error(exc: anthropic.APIStatusError) -> str:
    """Anthropic's own error type and message — "invalid_request_error: Your
    credit balance is too low…". It describes the problem, not the request."""
    body = exc.body
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return f"{error.get('type')}: {str(error.get('message'))[:300]}"
    return ""


async def get_card_reader() -> AsyncIterator[CardReader | None]:
    """The configured reader, or None when no API key is set.

    A FastAPI dependency, so the tests swap in a fake with
    app.dependency_overrides. One client per scan: scans are rare, and closing
    it when the request is done leaves no connections waiting on the garbage
    collector.
    """
    if not settings.anthropic_api_key:
        yield None
        return
    reader = ClaudeCardReader(settings.anthropic_api_key, settings.business_card_model)
    try:
        yield reader
    finally:
        await reader.aclose()
