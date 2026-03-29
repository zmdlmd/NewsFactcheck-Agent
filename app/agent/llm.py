from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


def build_model(model_name: str, base_url: str | None, api_key: str | None) -> ChatOpenAI:
    kwargs = {"model": model_name, "temperature": 0}
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key
    return ChatOpenAI(**kwargs)


def invoke_structured(model: ChatOpenAI, schema, system_prompt: str, user_prompt: str):
    structured = model.with_structured_output(schema)
    return structured.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )
