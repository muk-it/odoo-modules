from __future__ import annotations

from .base import ProviderBase
from .openai import OpenAIProvider
from .anthropic import AnthropicProvider
from .google import GoogleProvider


REGISTRY = {
    cls.name: cls
    for cls in (
        OpenAIProvider,
        AnthropicProvider,
        GoogleProvider,
    )
}
