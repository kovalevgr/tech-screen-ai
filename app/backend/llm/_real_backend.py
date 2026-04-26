"""Real Vertex AI backend using the ``google-genai`` async client.

This module is the **only** non-test backend module allowed to import a
model-provider SDK; the static guardrail at
``scripts/check-no-provider-sdk-imports.sh`` enforces the rule across the
backend tree.

Authentication uses Application Default Credentials exclusively
(constitution §6, ADR-013). The class constructor accepts NO credential
parameter — never a JSON service-account key, an inline private key, or
any opaque secret. Region is pinned at construction time per ADR-015
(``europe-west1`` for the MVP single-region deployment).

The wrapper translates ``google.api_core.exceptions.*`` raised by the
SDK into the typed wrapper errors per ``contracts/wrapper-contract.md``
§3 — this module re-raises the SDK exceptions unchanged so the wrapper's
:func:`tenacity.AsyncRetrying` loop can classify them.
"""

from __future__ import annotations

from typing import Any, Final

from google import genai
from google.genai import types

from app.backend.llm._backend_protocol import RawBackendResult

_DEFAULT_LOCATION: Final[str] = "europe-west1"


class RealVertexBackend:
    """Async wrapper over ``google.genai.Client.aio.models.generate_content``.

    Application Default Credentials only — no credential parameter is
    exposed. The Cloud Run revision in production injects the Workload
    Identity Federation principal via ADC; locally ADC resolves to the
    developer's ``gcloud auth application-default login`` identity.
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        location: str = _DEFAULT_LOCATION,
    ) -> None:
        # NOTE: NO `credentials` / `api_key` parameter. ADC only — see
        # ADR-013 and constitution §5/§6. The google-genai SDK resolves
        # ADC internally when `vertexai=True` and no explicit credentials
        # are passed.
        self._client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )

    async def generate(
        self,
        *,
        system_prompt: str,
        user_payload: str,
        json_schema: dict[str, Any] | None,
        model: str,
        temperature: float,
        max_output_tokens: int,
        timeout_s: float,
    ) -> RawBackendResult:
        """Issue one ``generate_content`` call and return the envelope.

        ``timeout_s`` is documented for protocol parity but the wall-clock
        timeout is enforced by the wrapper via :func:`asyncio.wait_for` —
        the SDK has no per-call timeout parameter.
        """
        del timeout_s
        config_kwargs: dict[str, Any] = {
            "system_instruction": system_prompt,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if json_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = json_schema
        config = types.GenerateContentConfig(**config_kwargs)

        response = await self._client.aio.models.generate_content(
            model=model,
            contents=user_payload,
            config=config,
        )
        text = response.text or ""
        usage = response.usage_metadata
        input_tokens = (usage.prompt_token_count or 0) if usage is not None else 0
        output_tokens = (usage.candidates_token_count or 0) if usage is not None else 0
        return RawBackendResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            model_version=response.model_version or model,
        )
