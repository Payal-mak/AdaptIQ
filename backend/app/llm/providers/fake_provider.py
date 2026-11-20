"""A scripted provider for tests. It never touches the network."""

from dataclasses import dataclass

from app.llm.base import LLMProvider, LLMResult

ScriptItem = str | LLMResult | Exception


@dataclass
class FakeCall:
    system: str
    user: str
    json_mode: bool
    temperature: float
    timeout: float


class FakeProvider(LLMProvider):
    """Each call to generate() consumes the next item of `script`:
    a str becomes a successful reply, an Exception is raised."""

    def __init__(
        self,
        script: list[ScriptItem],
        name: str = "fake",
        model: str = "fake-model",
        configured: bool = True,
        input_price_per_m: float = 0.0,
        output_price_per_m: float = 0.0,
    ) -> None:
        super().__init__(model, input_price_per_m, output_price_per_m)
        self.name = name
        self._configured = configured
        self.script = list(script)
        self.calls: list[FakeCall] = []

    @property
    def is_configured(self) -> bool:
        return self._configured

    def generate(
        self, system: str, user: str, json_mode: bool, temperature: float, timeout: float
    ) -> LLMResult:
        self.calls.append(FakeCall(system, user, json_mode, temperature, timeout))
        if not self.script:
            raise AssertionError(f"FakeProvider '{self.name}' was called more often than scripted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            return LLMResult(text=item, model=self.model, input_tokens=10, output_tokens=5)
        return item
