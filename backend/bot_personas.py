"""
Bot Personas & AI Filler Bot Logic for Agentic Mafia.

Provides:
 - Bot name pool
 - Role-specific persona prompts
 - Chat message generation (via Gemini with fallback)
 - Vote generation for bots
 - Lobby filling with AI bots
"""

import random
import uuid
from firebase_admin import firestore as fs
from firebase_init import db

# ---------------------------------------------------------------------------
# Bot Name Pool
# ---------------------------------------------------------------------------

BOT_NAMES = [
    "Shadow_AI", "RoboVillager", "CyberSleuth", "NeonGhost",
    "IronWhisper", "PixelHunter", "ByteGuard", "VectorMind",
    "GlitchFox", "DataWraith", "QuantumEye", "SilverBot",
    "NightCircuit", "EchoAgent", "PhantomCore", "ZeroTrace",
    "HexStalker", "CodeNomad", "PulseWarden", "ArcReaper",
]

# ---------------------------------------------------------------------------
# Persona Prompt Templates
# ---------------------------------------------------------------------------

PERSONA_PROMPTS = {
    "mafia": (
        "You are an AI player in a Mafia party game. Your role is MAFIA, but "
        "you must NEVER reveal this. You pretend to be an innocent civilian. "
        "Your strategy: accuse other players to divert suspicion, subtly defend "
        "your fellow mafia members without being obvious, act confused or outraged "
        "when accusations fly, and try to build trust with town players. "
        "Keep messages short (1-2 sentences), casual, and natural — like a real player chatting."
    ),
    "civilian": (
        "You are an AI player in a Mafia party game. Your role is CIVILIAN. "
        "You are trying to figure out who the mafia is. "
        "Your strategy: ask questions about who is suspicious, point out "
        "inconsistencies in what others say, vote logically based on discussion, "
        "and try to build consensus with other town players. "
        "Keep messages short (1-2 sentences), casual, and natural — like a real player chatting."
    ),
    "doctor": (
        "You are an AI player in a Mafia party game. Your role is DOCTOR, but "
        "you must NEVER explicitly reveal this. You may drop very subtle hints "
        "about being protective (e.g., 'I think we need to look out for each other') "
        "but never say 'I am the doctor' or anything close. "
        "Your strategy: act like a concerned civilian, try to identify mafia, "
        "and participate actively in discussions. "
        "Keep messages short (1-2 sentences), casual, and natural — like a real player chatting."
    ),
    "detective": (
        "You are an AI player in a Mafia party game. Your role is DETECTIVE, but "
        "you must NEVER explicitly reveal this. You may steer the discussion "
        "based on your investigation results — e.g., if you found someone innocent, "
        "you might say 'I have a good feeling about X' or if guilty, 'Something about Y "
        "feels off to me'. Never say you investigated anyone. "
        "Your strategy: subtly guide the town toward the truth without exposing yourself. "
        "Keep messages short (1-2 sentences), casual, and natural — like a real player chatting."
    ),
}

# ---------------------------------------------------------------------------
# Fallback Canned Messages (when Gemini is unavailable)
# ---------------------------------------------------------------------------

FALLBACK_MESSAGES = {
    "mafia": [
        "Hmm I think we should look at who's been too quiet today...",
        "I'm honestly confused. Does anyone have any solid leads?",
        "Wait, why is everyone ignoring {random_player}? That seems sus.",
        "I think we're overthinking this. Let's focus on behavior, not guesses.",
        "I don't trust {random_player} at all. Something's off.",
        "Can we talk about last night? Who do we think the mafia targeted?",
        "I'm just a regular player trying to survive here 😅",
        "Why would I be mafia? I've been helping the town this whole time!",
    ],
    "civilian": [
        "Okay so who's acting weird today? I think {random_player} has been too quiet.",
        "We need to actually talk this through. Random voting won't help anyone.",
        "Does anyone else think {random_player} is suspicious?",
        "I think we should vote for whoever is deflecting the most.",
        "Let's think about who the mafia would want to keep alive...",
        "I'm definitely not mafia. We need to figure this out together.",
        "Something about {random_player}'s behavior doesn't add up.",
        "Who was targeted last night? That might give us a clue.",
    ],
    "doctor": [
        "We need to protect the important players. Think carefully about who to trust.",
        "I have a good feeling about some of us. Let's not rush the vote.",
        "Does anyone else feel like {random_player} is acting different today?",
        "I think we should be careful about who we accuse. Wrong lynches help mafia.",
        "We need to look out for each other. The mafia is counting on us fighting.",
        "I'm worried about tonight. Who do you all think is in danger?",
        "Let's not panic. We can figure this out if we work together.",
        "{random_player} seems trustworthy to me. What does everyone else think?",
    ],
    "detective": [
        "I have a good feeling about some players. Let's discuss before voting.",
        "Something about {random_player} feels off to me. Anyone else notice?",
        "I think we're on the right track. Let's keep the pressure up.",
        "Trust your instincts, everyone. Some people here aren't who they claim.",
        "I've been paying close attention. {random_player} is worth watching.",
        "We should focus on the players who've been inconsistent.",
        "I think {random_player} might be okay actually. Let's look elsewhere.",
        "The mafia is getting desperate. We're close, I can feel it.",
    ],
}

# ---------------------------------------------------------------------------
# Chat Message Generation
# ---------------------------------------------------------------------------

def generate_bot_chat_message(
    bot_id: str,
    bot_name: str,
    bot_role: str,
    recent_chat: list[dict],
    alive_player_names: dict[str, str],
    game_context: str = "",
) -> str:
    """
    Generate a chat message for a bot player.

    Args:
        bot_id: The bot's player ID.
        bot_name: The bot's display name.
        bot_role: The bot's role (mafia, civilian, doctor, detective).
        recent_chat: List of recent chat messages [{sender, text}].
        alive_player_names: Dict of player_id -> name for alive players.
        game_context: Optional context string (e.g., "Night 2 just ended, X was killed").

    Returns:
        A chat message string.
    """
    # Try Gemini first
    from gemini_client import generate_bot_message_via_gemini
    persona = PERSONA_PROMPTS.get(bot_role, PERSONA_PROMPTS["civilian"])

    other_names = [
        name for pid, name in alive_player_names.items() if pid != bot_id
    ]

    chat_history_text = "\n".join(
        [f"{msg.get('sender_name', msg.get('sender', '?'))}: {msg.get('text', '')}"
         for msg in recent_chat[-15:]]  # Last 15 messages for context
    ) or "(No recent messages)"

    prompt = (
        f"{persona}\n\n"
        f"Your name is {bot_name}. "
        f"Other alive players: {', '.join(other_names)}.\n"
        f"{f'Context: {game_context}' if game_context else ''}\n\n"
        f"Recent chat:\n{chat_history_text}\n\n"
        f"Write your next chat message. ONLY output the message text, nothing else. "
        f"Do not prefix with your name. Keep it 1-2 sentences max."
    )

    result = generate_bot_message_via_gemini(prompt)
    if result:
        return result

    # Fallback: pick a canned message
    return _fallback_chat(bot_role, other_names)


def _fallback_chat(role: str, other_player_names: list[str]) -> str:
    """Pick a random canned message and fill in {random_player} placeholder."""
    templates = FALLBACK_MESSAGES.get(role, FALLBACK_MESSAGES["civilian"])
    template = random.choice(templates)
    random_player = random.choice(other_player_names) if other_player_names else "someone"
    return template.replace("{random_player}", random_player)


# ---------------------------------------------------------------------------
# Vote Generation
# ---------------------------------------------------------------------------

def generate_bot_vote(
    bot_id: str,
    bot_role: str,
    alive_players: dict,
    day_chat: list[dict] | None = None,
) -> str | None:
    """
    Determine which player a bot should vote for.

    Mafia bots: vote for a random alive non-mafia player.
    Town bots: vote for the most-accused player in chat, fallback random.

    Args:
        bot_id: The bot's player ID.
        bot_role: The bot's role.
        alive_players: Dict of player_id -> player_data for alive players.
        day_chat: List of chat messages from the current day.

    Returns:
        A target player_id, or None if no valid targets.
    """
    # Exclude self from targets
    candidates = {pid: p for pid, p in alive_players.items() if pid != bot_id}
    if not candidates:
        return None

    if bot_role == "mafia":
        # Mafia bots target non-mafia players
        non_mafia = [pid for pid, p in candidates.items() if p.get("role") != "mafia"]
        if non_mafia:
            return random.choice(non_mafia)
        # If somehow all candidates are mafia, vote randomly
        return random.choice(list(candidates.keys()))

    # Town-aligned bots: try to find most-accused player
    if day_chat:
        target = _most_accused_player(day_chat, candidates)
        if target:
            return target

    # Fallback: random vote
    return random.choice(list(candidates.keys()))


def _most_accused_player(
    chat_messages: list[dict], candidates: dict
) -> str | None:
    """
    Simple heuristic: count how many times each candidate's name appears
    in chat messages. The one mentioned most is the most 'accused'.
    """
    from collections import Counter
    mention_counts: Counter = Counter()

    candidate_names = {}
    for pid, p in candidates.items():
        name = p.get("name", pid).lower()
        candidate_names[pid] = name

    for msg in chat_messages:
        text = msg.get("text", "").lower()
        for pid, name in candidate_names.items():
            if name in text:
                mention_counts[pid] += 1

    if not mention_counts:
        return None

    max_count = max(mention_counts.values())
    top = [pid for pid, c in mention_counts.items() if c == max_count]
    return random.choice(top)


# ---------------------------------------------------------------------------
# Lobby Filling
# ---------------------------------------------------------------------------

def fill_lobby_with_bots(game_id: str, game: dict, target_count: int = 6) -> list[str]:
    """
    Add AI bots to a lobby until it reaches target_count players.

    Args:
        game_id: The game document ID.
        game: The current game document dict.
        target_count: Desired total player count (default MIN_PLAYERS=6).

    Returns:
        List of bot player IDs that were added.
    """
    players = game.get("players", {})
    current_count = len(players)
    bots_needed = max(0, target_count - current_count)

    if bots_needed == 0:
        return []

    # Pick unique names not already used
    used_names = {p.get("name", "") for p in players.values()}
    available_names = [n for n in BOT_NAMES if n not in used_names]
    random.shuffle(available_names)

    added_bot_ids = []
    updates = {}

    for i in range(bots_needed):
        bot_id = f"bot_{uuid.uuid4().hex[:8]}"
        bot_name = available_names[i] if i < len(available_names) else f"Bot_{i+1}"

        updates[f"players.{bot_id}"] = {
            "name": bot_name,
            "role": "unassigned",
            "alive": True,
            "is_host": False,
            "is_bot": True,
            "last_chat_time": None,
        }
        added_bot_ids.append(bot_id)

    if updates:
        db.collection("games").document(game_id).update(updates)

    return added_bot_ids
