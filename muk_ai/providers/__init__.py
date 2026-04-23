from .base import ProviderBase
from .openai import OpenAIProvider
from .anthropic import AnthropicProvider


REGISTRY = {
    cls.name: cls for cls in (
        OpenAIProvider,
        AnthropicProvider,
    )
}
