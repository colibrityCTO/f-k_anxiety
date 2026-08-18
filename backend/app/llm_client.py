"""Client LLM : Anthropic Claude en principal, OpenAI en fallback automatique.

Les deux clients sont des singletons paresseux (créés au premier usage, réutilisés
ensuite : les connexions HTTP sont ainsi mutualisées). L'orchestration passe par
LangChain (`langchain_anthropic.ChatAnthropic` / `langchain_openai.ChatOpenAI`), ce
qui donne une interface unique pour `ainvoke` et `astream`.

Si aucune clé n'est configurée, `LLMUnavailable` est levée : les appelants
basculent alors sur l'analyse déterministe locale (`app/signals.py`) et
l'indiquent explicitement à l'utilisateur.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_anthropic_chat: Any | None = None
_openai_chat: Any | None = None


class LLMUnavailable(RuntimeError):
    """Aucun fournisseur LLM utilisable (pas de clé, ou tous en échec)."""


@dataclass
class LLMResult:
    text: str
    engine: str
    fallback_used: bool = False
    errors: list[str] = field(default_factory=list)


# --- Singletons -------------------------------------------------------------


def get_anthropic_chat() -> Any | None:
    global _anthropic_chat
    if not settings.has_anthropic:
        return None
    if _anthropic_chat is None:
        with _lock:
            if _anthropic_chat is None:
                try:
                    from langchain_anthropic import ChatAnthropic
                except ImportError as exc:
                    # Clé fournie mais paquet absent : on dégrade vers le
                    # fournisseur suivant plutôt que de renvoyer une 500.
                    logger.error("langchain-anthropic non installé : %s", exc)
                    return None

                _anthropic_chat = ChatAnthropic(
                    model=settings.anthropic_model,
                    api_key=settings.anthropic_api_key,
                    max_tokens=settings.llm_max_tokens,
                    temperature=settings.llm_temperature,
                    timeout=120,
                    max_retries=2,
                )
                logger.info("Client Anthropic initialisé (%s)", settings.anthropic_model)
    return _anthropic_chat


def get_openai_chat() -> Any | None:
    global _openai_chat
    if not settings.has_openai:
        return None
    if _openai_chat is None:
        with _lock:
            if _openai_chat is None:
                try:
                    from langchain_openai import ChatOpenAI
                except ImportError as exc:
                    logger.error("langchain-openai non installé : %s", exc)
                    return None

                _openai_chat = ChatOpenAI(
                    model=settings.openai_model,
                    api_key=settings.openai_api_key,
                    max_tokens=settings.llm_max_tokens,
                    temperature=settings.llm_temperature,
                    timeout=120,
                    max_retries=2,
                )
                logger.info("Client OpenAI initialisé (%s)", settings.openai_model)
    return _openai_chat


def _providers() -> list[tuple[str, Any]]:
    """Fournisseurs disponibles, dans l'ordre de préférence."""
    out: list[tuple[str, Any]] = []
    anthropic = get_anthropic_chat()
    if anthropic is not None:
        out.append((f"anthropic:{settings.anthropic_model}", anthropic))
    openai = get_openai_chat()
    if openai is not None:
        out.append((f"openai:{settings.openai_model}", openai))
    return out


def available_engines() -> list[str]:
    return [name for name, _ in _providers()]


def _messages(system: str, user: str) -> list[Any]:
    from langchain_core.messages import HumanMessage, SystemMessage

    return [SystemMessage(content=system), HumanMessage(content=user)]


# --- Complétion -------------------------------------------------------------


async def complete(system: str, user: str) -> LLMResult:
    """Appel non streamé, avec bascule automatique sur le fournisseur suivant."""
    providers = _providers()
    if not providers:
        raise LLMUnavailable("Aucune clé d'API LLM configurée.")

    errors: list[str] = []
    for index, (engine, client) in enumerate(providers):
        try:
            response = await client.ainvoke(_messages(system, user))
            text = response.content
            if isinstance(text, list):  # blocs de contenu Anthropic
                text = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in text
                )
            return LLMResult(text=text, engine=engine, fallback_used=index > 0, errors=errors)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - on veut vraiment tout rattraper ici
            logger.warning("Échec du fournisseur %s : %s", engine, exc)
            errors.append(f"{engine}: {exc}")

    raise LLMUnavailable("Tous les fournisseurs LLM ont échoué : " + " | ".join(errors))


# --- Streaming --------------------------------------------------------------


async def stream(system: str, user: str) -> AsyncIterator[tuple[str, str]]:
    """Streaming de tokens. Yield des tuples (type, valeur) :

    - ("engine", "anthropic:claude-opus-5") émis une fois au premier token ;
    - ("token", "…") pour chaque fragment de texte ;
    - ("error", "message") si tous les fournisseurs échouent.

    La bascule vers le fallback n'est possible qu'avant le premier token : une
    fois du texte envoyé au client, on ne rejoue pas la réponse depuis le début.
    """
    providers = _providers()
    if not providers:
        yield ("error", "Aucune clé d'API LLM configurée.")
        return

    errors: list[str] = []
    for engine, client in providers:
        emitted = False
        try:
            async for chunk in client.astream(_messages(system, user)):
                piece = chunk.content
                if isinstance(piece, list):
                    piece = "".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in piece
                    )
                if not piece:
                    continue
                if not emitted:
                    emitted = True
                    yield ("engine", engine)
                yield ("token", piece)
            if emitted:
                return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Échec du streaming %s : %s", engine, exc)
            errors.append(f"{engine}: {exc}")
            if emitted:
                # Réponse déjà partiellement envoyée : on signale sans rejouer.
                yield ("error", f"Interruption du flux ({engine}).")
                return

    yield ("error", "Tous les fournisseurs LLM ont échoué : " + " | ".join(errors))
