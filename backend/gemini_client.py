"""
Gemini API client for AI-powered game features.
Handles mafia consensus analysis, dramatic narration generation,
lynch narration, and bot message generation.
Falls back to deterministic logic if the API is unavailable.
"""

import os
import json
import re
from dotenv import load_dotenv

load_dotenv()

GEMINI_ENABLED = False
model = None

try:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        GEMINI_ENABLED = True
        print("[Gemini] Initialized successfully.")
    else:
        print("[Gemini] No API key found. AI features disabled; using fallback logic.")
except ImportError:
    print("[Gemini] google-generativeai not installed. AI features disabled.")
except Exception as e:
    print(f"[Gemini] Initialization failed: {e}. AI features disabled.")


# ---------------------------------------------------------------------------
# Mafia Chat Consensus Analysis
# ---------------------------------------------------------------------------

def analyze_mafia_chat(chat_messages: list[dict], votes: dict[str, str]) -> str | None:
    """
    Analyze mafia chat and votes to determine consensus target.

    Args:
        chat_messages: List of dicts with 'sender' and 'text' keys.
        votes: Dict mapping mafia player_id -> target player_id.

    Returns:
        A player_id string representing the chosen target, or None on failure.
    """
    if not GEMINI_ENABLED or model is None:
        return None

    try:
        votes_json = json.dumps(votes, indent=2)
        chat_text = "\n".join(
            [f"{msg['sender']}: {msg['text']}" for msg in chat_messages]
        )

        prompt = (
            "You are a mafia game coordinator. The mafia members had these votes:\n"
            f"{votes_json}\n\n"
            "And this chat during the night:\n"
            f"{chat_text}\n\n"
            "Determine the target they most likely want to kill. "
            "Reply with ONLY the player ID string, e.g., 'player_1'. "
            "Do not include any other text or explanation."
        )

        response = model.generate_content(prompt)
        result = response.text.strip().strip("'\"")

        # Basic validation: result should look like a player ID (non-empty, no spaces)
        if result and " " not in result and len(result) < 100:
            return result

        return None
    except Exception as e:
        print(f"[Gemini] analyze_mafia_chat failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Night Narration
# ---------------------------------------------------------------------------

def generate_night_narration(
    killed_player: str | None,
    saved: bool,
    detective_target: str | None,
    detective_result: str | None,
    night_number: int,
    saved_player: str | None = None,       # ADDED: name of the player who was saved
) -> str:
    """
    Generate a dramatic narration for the night's events.

    Args:
        killed_player: Name of the killed player, or None if saved/no kill.
        saved: Whether the doctor saved the target.
        detective_target: Name of the investigated player.
        detective_result: "guilty" or "innocent".
        night_number: Current night number.
        saved_player: Name of the player the doctor saved (used when saved=True).

    Returns:
        A narration string.
    """
    if not GEMINI_ENABLED or model is None:
        return _fallback_narration(
            killed_player, saved, detective_target, detective_result, night_number
        )

    try:
        events = []
        if saved:
            target_name = saved_player or killed_player or "someone"
            events.append(
                f"The mafia attempted to kill {target_name}, but the doctor saved them!"
            )
        elif killed_player:
            events.append(f"The mafia killed {killed_player} during the night.")
        else:
            events.append("The mafia could not agree on a target. No one was killed.")

        if detective_target:
            events.append(
                f"The detective investigated {detective_target} and found them {detective_result}."
            )

        events_text = " ".join(events)

        prompt = (
            f"You are a dramatic narrator for a Mafia party game. It is Night {night_number}. "
            f"Here is what happened: {events_text} "
            "Narrate these events in 2-3 sentences with a dramatic, suspenseful tone. "
            "Do not reveal the detective's findings to the public. "
            "Only narrate who died or if someone was miraculously saved."
        )

        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"[Gemini] generate_night_narration failed: {e}")
        return _fallback_narration(
            killed_player, saved, detective_target, detective_result, night_number
        )


def _fallback_narration(
    killed_player: str | None,
    saved: bool,
    detective_target: str | None,
    detective_result: str | None,
    night_number: int,
) -> str:
    """Deterministic fallback narration when Gemini is unavailable."""
    lines = [f"☾ Night {night_number} has ended."]

    if saved:
        lines.append(
            "The town awakes to find everyone alive. "
            "Someone was targeted, but a guardian angel watched over them."
        )
    elif killed_player:
        lines.append(
            f"The town awakes to tragic news... {killed_player} was found dead. "
            "The mafia has struck again."
        )
    else:
        lines.append(
            "The town awakes peacefully. No one was harmed during the night."
        )

    return " ".join(lines)


# ---------------------------------------------------------------------------
# Lynch Narration  [ADDED]
# ---------------------------------------------------------------------------

def generate_lynch_narration(
    lynched_name: str,
    lynched_role: str,
    day_number: int,
) -> str:
    """
    Generate a dramatic narration for a lynch event.

    Args:
        lynched_name: Display name of the lynched player.
        lynched_role: The role that was revealed upon lynching.
        day_number: Current day number.

    Returns:
        A narration string.
    """
    if not GEMINI_ENABLED or model is None:
        return _fallback_lynch_narration(lynched_name, lynched_role, day_number)

    try:
        was_mafia = lynched_role == "mafia"
        outcome = (
            f"{lynched_name} was revealed to be MAFIA! The town made the right call."
            if was_mafia
            else f"{lynched_name} was revealed to be a {lynched_role}. An innocent has fallen."
        )

        prompt = (
            f"You are a dramatic narrator for a Mafia party game. It is Day {day_number}. "
            f"The town just voted to lynch {lynched_name}. {outcome} "
            "Narrate this event in 2-3 sentences with dramatic flair. "
            "Mention the revealed role and whether the town made a good or tragic decision."
        )

        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"[Gemini] generate_lynch_narration failed: {e}")
        return _fallback_lynch_narration(lynched_name, lynched_role, day_number)


def _fallback_lynch_narration(
    lynched_name: str,
    lynched_role: str,
    day_number: int,
) -> str:
    """Deterministic fallback narration for lynch events."""
    if lynched_role == "mafia":
        return (
            f"⚖️ Day {day_number}: The town has spoken! {lynched_name} was dragged to "
            f"the gallows and revealed to be MAFIA. Justice has been served!"
        )
    else:
        return (
            f"⚖️ Day {day_number}: The town has spoken! {lynched_name} was lynched, "
            f"but was revealed to be a {lynched_role}. "
            "An innocent soul has been lost to mob justice."
        )


# ---------------------------------------------------------------------------
# Bot Message Generation  [ADDED]
# ---------------------------------------------------------------------------

def generate_bot_message_via_gemini(prompt: str) -> str | None:
    """
    Generate a chat message for a bot player using Gemini.

    Args:
        prompt: The fully constructed prompt with persona and context.

    Returns:
        A message string, or None on failure.
    """
    if not GEMINI_ENABLED or model is None:
        return None

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Sanity check: message shouldn't be absurdly long
        if text and len(text) < 300:
            return text
        elif text:
            # Truncate to first sentence
            first_sentence = text.split(".")[0] + "."
            return first_sentence[:280]
        return None
    except Exception as e:
        print(f"[Gemini] generate_bot_message failed: {e}")
        return None
