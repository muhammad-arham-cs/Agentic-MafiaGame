"""
Core game logic for Agentic Mafia.
Contains role distribution, phase transitions, night resolution,
win condition checks, and all helper functions.
"""

import random
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore as fs
from firebase_init import db
from gemini_client import analyze_mafia_chat, generate_night_narration, generate_lynch_narration

# ---------------------------------------------------------------------------
# Constants & Configuration
# ---------------------------------------------------------------------------

ROLE_DISTRIBUTION = {
    6:  {"mafia": 2, "detective": 1, "doctor": 1, "civilian": 2},
    7:  {"mafia": 2, "detective": 1, "doctor": 1, "civilian": 3},
    8:  {"mafia": 2, "detective": 1, "doctor": 1, "civilian": 4},
    9:  {"mafia": 3, "detective": 1, "doctor": 1, "civilian": 4},
    10: {"mafia": 3, "detective": 1, "doctor": 1, "civilian": 5},
    11: {"mafia": 3, "detective": 1, "doctor": 1, "civilian": 6},
    12: {"mafia": 4, "detective": 1, "doctor": 1, "civilian": 6},
}

MIN_PLAYERS = 6
MAX_PLAYERS = 12

# Phase durations (seconds)
MAFIA_PHASE_DURATION = 45
DOCTOR_PHASE_DURATION = 15
DETECTIVE_PHASE_DURATION = 15
DAY_PHASE_DURATION = 300        # 5 minutes
VOTING_PHASE_DURATION = 180     # 3 minutes

AFK_THRESHOLD_SECONDS = 90
DOCTOR_SELF_PROTECT_MAX = 1
DOCTOR_OTHER_PROTECT_MAX = 2

# Load blocked phrases
try:
    with open("blocked_phrases.json", "r", encoding="utf-8") as f:
        BLOCKED_PHRASES: list[str] = [p.lower() for p in json.load(f)]
except FileNotFoundError:
    print("[WARNING] blocked_phrases.json not found. Chat filtering disabled.")
    BLOCKED_PHRASES = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _get_game_ref(game_id: str):
    return db.collection("games").document(game_id)


def _get_game(game_id: str) -> dict | None:
    doc = _get_game_ref(game_id).get()
    return doc.to_dict() if doc.exists else None


def _alive_players(game: dict) -> dict:
    """Return dict of player_id -> player data for alive players."""
    return {pid: p for pid, p in game.get("players", {}).items() if p.get("alive")}


def _alive_mafia(game: dict) -> dict:
    return {pid: p for pid, p in _alive_players(game).items() if p.get("role") == "mafia"}


def _alive_non_mafia(game: dict) -> dict:
    return {pid: p for pid, p in _alive_players(game).items() if p.get("role") != "mafia"}


def _get_night_number(game: dict) -> int:
    return game.get("night_number", 1)


def _get_day_number(game: dict) -> int:
    return game.get("day_number", 1)


def get_alive_player_ids(game: dict) -> list[str]:
    """Return list of player IDs where alive == True.  [ADDED – bug fix]"""
    return [pid for pid, p in game.get("players", {}).items() if p.get("alive")]


def get_active_player_count(game: dict) -> int:
    """Count living players whose last_chat_time is within AFK_THRESHOLD_SECONDS."""
    now = _now_utc()
    count = 0
    for pid, p in _alive_players(game).items():
        lct = p.get("last_chat_time")
        if lct:
            if isinstance(lct, datetime):
                delta = (now - lct.replace(tzinfo=timezone.utc if lct.tzinfo is None else lct.tzinfo)).total_seconds()
            else:
                delta = AFK_THRESHOLD_SECONDS + 1
            if delta <= AFK_THRESHOLD_SECONDS:
                count += 1
    return count


def is_message_blocked(text: str) -> bool:
    """Check if a message contains any blocked phrase (case-insensitive substring)."""
    lower = text.lower()
    return any(phrase in lower for phrase in BLOCKED_PHRASES)


# ---------------------------------------------------------------------------
# Role Assignment
# ---------------------------------------------------------------------------

def assign_roles(player_ids: list[str]) -> dict[str, str]:
    """Randomly assign roles to players based on ROLE_DISTRIBUTION."""
    count = len(player_ids)
    if count not in ROLE_DISTRIBUTION:
        raise ValueError(f"Unsupported player count: {count}. Must be {MIN_PLAYERS}-{MAX_PLAYERS}.")

    dist = ROLE_DISTRIBUTION[count]
    roles: list[str] = []
    for role, num in dist.items():
        roles.extend([role] * num)

    random.shuffle(roles)
    shuffled_ids = list(player_ids)
    random.shuffle(shuffled_ids)
    return dict(zip(shuffled_ids, roles))


# ---------------------------------------------------------------------------
# Doctor Protection Limits
# ---------------------------------------------------------------------------

def check_doctor_protection_limit(doctor_id: str, target_id: str, game_id: str) -> tuple[bool, str]:
    """
    Check if the doctor can protect the target.
    Returns (allowed: bool, reason: str).
    """
    history_ref = db.collection("doctor_history").document(game_id)
    docs = history_ref.collection("records").where("protected_by", "==", doctor_id).stream()

    self_count = 0
    target_count = 0
    for doc in docs:
        d = doc.to_dict()
        if d.get("target") == doctor_id:
            self_count += 1
        if d.get("target") == target_id:
            target_count += 1

    if doctor_id == target_id:
        if self_count >= DOCTOR_SELF_PROTECT_MAX:
            return False, f"Self-protect limit reached ({DOCTOR_SELF_PROTECT_MAX} total)."
        return True, ""

    if target_count >= DOCTOR_OTHER_PROTECT_MAX:
        return False, f"This player has already been protected {DOCTOR_OTHER_PROTECT_MAX} times."

    return True, ""


def record_doctor_protection(doctor_id: str, target_id: str, game_id: str, night: int):
    db.collection("doctor_history").document(game_id).collection("records").add({
        "protected_by": doctor_id,
        "target": target_id,
        "night": night,
        "timestamp": fs.SERVER_TIMESTAMP,
    })


# ---------------------------------------------------------------------------
# Detective Investigation Limits
# ---------------------------------------------------------------------------

def check_detective_investigation_limit(detective_id: str, target_id: str, game_id: str) -> tuple[bool, str]:
    """Check if this target has already been investigated."""
    if detective_id == target_id:
        return False, "Cannot investigate yourself."

    history_ref = db.collection("detective_history").document(game_id)
    docs = history_ref.collection("records").where("target", "==", target_id).stream()
    if any(True for _ in docs):
        return False, "This player has already been investigated."

    return True, ""


def check_detective_has_targets(detective_id: str, game_id: str, game: dict) -> bool:
    """Check if there are any uninvestigated alive players (excluding detective)."""
    alive = _alive_players(game)
    history_ref = db.collection("detective_history").document(game_id)
    investigated = set()
    for doc in history_ref.collection("records").stream():
        investigated.add(doc.to_dict().get("target"))

    for pid in alive:
        if pid != detective_id and pid not in investigated:
            return True
    return False


def record_detective_investigation(detective_id: str, target_id: str, game_id: str, night: int, result: str):
    db.collection("detective_history").document(game_id).collection("records").add({
        "investigated_by": detective_id,
        "target": target_id,
        "night": night,
        "result": result,
        "timestamp": fs.SERVER_TIMESTAMP,
    })


# ---------------------------------------------------------------------------
# Mafia Consensus
# ---------------------------------------------------------------------------

def resolve_mafia_target(game_id: str, game: dict) -> str | None:
    """
    Determine the mafia's chosen target for the night.
    Uses votes, chat analysis via Gemini, and fallback logic.
    """
    # Gather mafia votes
    votes_ref = db.collection("mafia_votes").document(game_id).collection("night_votes")
    night = _get_night_number(game)
    vote_docs = votes_ref.where("night", "==", night).stream()

    votes: dict[str, str] = {}
    first_voter_target: str | None = None
    first_vote_time = None

    for doc in vote_docs:
        d = doc.to_dict()
        voter = d.get("voter")
        target = d.get("target")
        ts = d.get("timestamp")
        if voter and target:
            votes[voter] = target
            if first_vote_time is None or (ts and ts < first_vote_time):
                first_vote_time = ts
                first_voter_target = target

    # Handle AFK mafia: transfer their votes to first voter's target
    alive_mafia = _alive_mafia(game)
    for mid in alive_mafia:
        if mid not in votes and first_voter_target:
            votes[mid] = first_voter_target

    if not votes:
        return None

    # Check unanimity
    targets = list(votes.values())
    if len(set(targets)) == 1:
        return targets[0]

    # Split votes – try Gemini analysis
    chat_messages = _get_mafia_chat_messages(game_id, night)
    ai_target = analyze_mafia_chat(chat_messages, votes)

    # Validate AI target is a living player
    alive = _alive_players(game)
    if ai_target and ai_target in alive:
        return ai_target

    # Fallback: most votes; tie → random among top
    return _majority_or_random(targets, alive)


def _get_mafia_chat_messages(game_id: str, night: int) -> list[dict]:
    msgs = []
    docs = (
        db.collection("mafia_chat").document(game_id)
        .collection("messages")
        .where("night_number", "==", night)
        .order_by("timestamp")
        .stream()
    )
    for doc in docs:
        d = doc.to_dict()
        msgs.append({"sender": d.get("sender", ""), "text": d.get("text", "")})
    return msgs


def _majority_or_random(targets: list[str], alive: dict) -> str | None:
    counts = Counter(t for t in targets if t in alive)
    if not counts:
        return None
    max_count = max(counts.values())
    top = [t for t, c in counts.items() if c == max_count]
    # "First to reach max votes" – since we can't track exact order here, pick random among top
    return random.choice(top) if len(top) > 1 else top[0]


# ---------------------------------------------------------------------------
# Night Resolution
# ---------------------------------------------------------------------------

def apply_night_results(game_id: str) -> dict:
    """
    Resolve all night actions and return a summary dict.
    Returns: { "killed": player_id|None, "saved": bool,
               "detective_target": player_id|None, "detective_result": str|None }
    """
    game = _get_game(game_id)
    if not game:
        return {"error": "Game not found"}

    night = _get_night_number(game)
    mafia_target = resolve_mafia_target(game_id, game)
    doctor_target = game.get("doctor_target")
    detective_target = game.get("detective_target")
    detective_result = game.get("detective_result")

    saved = False
    killed = None

    if mafia_target:
        if mafia_target == doctor_target:
            saved = True
        else:
            killed = mafia_target
            # Kill the player
            _get_game_ref(game_id).update({
                f"players.{mafia_target}.alive": False,
            })

    # Generate narration
    killed_name = None
    if killed:
        killed_name = game["players"].get(killed, {}).get("name", killed)

    # ADDED: compute saved player name for narration
    saved_player_name = None
    if saved and mafia_target:
        saved_player_name = game["players"].get(mafia_target, {}).get("name", mafia_target)

    det_target_name = None
    if detective_target:
        det_target_name = game["players"].get(detective_target, {}).get("name", detective_target)

    narration = generate_night_narration(
        killed_player=killed_name,
        saved=saved,
        detective_target=det_target_name,
        detective_result=detective_result,
        night_number=night,
        saved_player=saved_player_name,       # ADDED
    )

    # Store narration and clear night fields
    _get_game_ref(game_id).update({
        "last_narration": narration,
        "mafia_target": None,
        "doctor_target": None,
        "detective_target": None,
        "detective_result": None,
    })

    return {
        "killed": killed,
        "killed_name": killed_name,
        "saved": saved,
        "detective_target": detective_target,
        "detective_result": detective_result,
        "narration": narration,
        "night_number": night,
    }


# ---------------------------------------------------------------------------
# Win Condition
# ---------------------------------------------------------------------------

def check_win_condition(game_id: str) -> dict | None:
    """
    Check if the game has been won.
    Returns { "winner": "mafia"|"civilians", "reason": str } or None.
    """
    game = _get_game(game_id)
    if not game:
        return None

    mode = game.get("mode", "standard")
    mafia_count = len(_alive_mafia(game))
    non_mafia_count = len(_alive_non_mafia(game))

    if mafia_count == 0:
        _get_game_ref(game_id).update({
            "status": "gameover",
            "winning_team": "civilians",
        })
        return {"winner": "civilians", "reason": "All mafia have been eliminated!"}

    if mode == "standard":
        if mafia_count >= non_mafia_count:
            _get_game_ref(game_id).update({
                "status": "gameover",
                "winning_team": "mafia",
            })
            return {"winner": "mafia", "reason": "Mafia outnumber the civilians!"}
    else:  # fight_to_death
        if non_mafia_count == 0:
            _get_game_ref(game_id).update({
                "status": "gameover",
                "winning_team": "mafia",
            })
            return {"winner": "mafia", "reason": "All civilians have been eliminated!"}

    return None


# ---------------------------------------------------------------------------
# Phase Transitions
# ---------------------------------------------------------------------------

def _phase_elapsed(game: dict) -> bool:
    """Check if the current phase's timer has expired."""
    start = game.get("phase_start_time")
    duration = game.get("phase_duration_seconds", 0)
    if not start or not duration:
        return False
    if isinstance(start, datetime):
        now = _now_utc()
        start_utc = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start
        elapsed = (now - start_utc).total_seconds()
        return elapsed >= duration
    return False


def _start_phase(game_id: str, status: str, sub_phase: str | None,
                 duration: int, extra_updates: dict | None = None):
    """Helper to transition to a new phase."""
    updates = {
        "status": status,
        "phase_start_time": fs.SERVER_TIMESTAMP,
        "phase_duration_seconds": duration,
    }
    if sub_phase is not None:
        updates["night_phase_state"] = sub_phase
    if extra_updates:
        updates.update(extra_updates)
    _get_game_ref(game_id).update(updates)


def advance_phase(game_id: str, force: bool = False) -> dict:
    """
    Main state-machine driver. Checks timers and conditions, then
    transitions to the next appropriate phase.
    Returns a status dict describing what happened.
    """
    game = _get_game(game_id)
    if not game:
        return {"error": "Game not found"}

    status = game.get("status")
    if status == "gameover":
        return {"status": "gameover", "winning_team": game.get("winning_team")}

    if status == "lobby":
        return {"error": "Game has not started yet"}

    elapsed = _phase_elapsed(game) or force

    # --- NIGHT PHASE ---
    if status == "night":
        return _advance_night(game_id, game, elapsed)

    # --- DAY PHASE ---
    if status == "day":
        return _advance_day(game_id, game, elapsed)

    # --- VOTING PHASE ---
    if status == "voting":
        return _advance_voting(game_id, game, elapsed)

    return {"error": f"Unknown status: {status}"}


def _advance_night(game_id: str, game: dict, elapsed: bool) -> dict:
    sub = game.get("night_phase_state", "mafia")

    if sub == "mafia":
        # FIX: Bug 2 – trigger bot mafia votes before checking if all voted
        execute_bot_night_actions(game_id, game, "mafia")
        # Re-read game to see bot votes
        game = _get_game(game_id)
        all_voted = _all_mafia_voted(game_id, game)
        if elapsed or all_voted:
            # Move to doctor phase
            _start_phase(game_id, "night", "doctor", DOCTOR_PHASE_DURATION)
            return {"action": "night_doctor_phase_started", "duration": DOCTOR_PHASE_DURATION}
        return {"status": "waiting", "phase": "night", "sub_phase": "mafia"}

    if sub == "doctor":
        # FIX: Bug 2 – trigger bot doctor action before checking
        execute_bot_night_actions(game_id, game, "doctor")
        game = _get_game(game_id)
        doctor_acted = game.get("doctor_target") is not None
        if elapsed or doctor_acted:
            _start_phase(game_id, "night", "detective", DETECTIVE_PHASE_DURATION)
            return {"action": "night_detective_phase_started", "duration": DETECTIVE_PHASE_DURATION}
        return {"status": "waiting", "phase": "night", "sub_phase": "doctor"}

    if sub == "detective":
        # FIX: Bug 2 – trigger bot detective action before checking
        execute_bot_night_actions(game_id, game, "detective")
        game = _get_game(game_id)
        detective_acted = game.get("detective_target") is not None
        if elapsed or detective_acted:
            # Resolve entire night
            results = apply_night_results(game_id)

            # Check win condition
            win = check_win_condition(game_id)
            if win:
                return {"action": "gameover", **win, "night_results": results}

            # Transition to day
            night = _get_night_number(game)
            _start_phase(game_id, "day", None, DAY_PHASE_DURATION, extra_updates={
                "night_phase_state": "done",
                "vote_now_presses": [],
                "day_number": night,  # day N follows night N
            })
            return {"action": "day_started", "night_results": results, "duration": DAY_PHASE_DURATION}

        return {"status": "waiting", "phase": "night", "sub_phase": "detective"}

    return {"error": f"Unknown night sub-phase: {sub}"}


def _all_mafia_voted(game_id: str, game: dict) -> bool:
    alive_mafia_ids = set(_alive_mafia(game).keys())
    if not alive_mafia_ids:
        return True
    night = _get_night_number(game)
    votes_ref = db.collection("mafia_votes").document(game_id).collection("night_votes")
    vote_docs = votes_ref.where("night", "==", night).stream()
    voters = {d.to_dict().get("voter") for d in vote_docs}
    return alive_mafia_ids.issubset(voters)


def _advance_day(game_id: str, game: dict, elapsed: bool) -> dict:
    vote_now_triggered = game.get("vote_now_triggered", False)
    if elapsed or vote_now_triggered:
        _start_phase(game_id, "voting", None, VOTING_PHASE_DURATION, extra_updates={
            "vote_now_triggered": False,
        })
        return {"action": "voting_started", "duration": VOTING_PHASE_DURATION}
    return {"status": "waiting", "phase": "day"}


def _advance_voting(game_id: str, game: dict, elapsed: bool) -> dict:
    alive = _alive_players(game)
    alive_count = len(alive)
    majority = (alive_count // 2) + 1

    # Tally votes
    votes_ref = db.collection("votes").document(game_id).collection("round_votes")
    day = _get_day_number(game)
    vote_docs = votes_ref.where("day", "==", day).stream()

    vote_counts: Counter = Counter()
    first_reach: dict[str, datetime] = {}

    for doc in vote_docs:
        d = doc.to_dict()
        target = d.get("target")
        ts = d.get("timestamp")
        if target and target in alive:
            vote_counts[target] += 1
            # Track first time each target reached their current count
            if target not in first_reach or (ts and ts < first_reach[target]):
                first_reach[target] = ts

    # Check majority
    majority_target = None
    for target, count in vote_counts.items():
        if count >= majority:
            majority_target = target
            break

    if majority_target:
        return _lynch_player(game_id, game, majority_target, day)

    if elapsed:
        if vote_counts:
            max_count = max(vote_counts.values())
            top = [t for t, c in vote_counts.items() if c == max_count]
            # Tie-break: first to reach max
            if len(top) == 1:
                return _lynch_player(game_id, game, top[0], day)
            # Among tied, pick the one who reached max_count first
            earliest = min(top, key=lambda t: first_reach.get(t, _now_utc()))
            return _lynch_player(game_id, game, earliest, day)
        else:
            # No votes cast – skip lynch
            return _start_new_night(game_id, game)

    return {"status": "waiting", "phase": "voting", "vote_counts": dict(vote_counts)}


def _lynch_player(game_id: str, game: dict, target_id: str, day: int) -> dict:
    player = game["players"].get(target_id, {})
    lynched_name = player.get("name", target_id)
    lynched_role = player.get("role", "unknown")

    _get_game_ref(game_id).update({
        f"players.{target_id}.alive": False,
    })

    # ADDED: Generate and store lynch narration  [BUG FIX]
    narration = generate_lynch_narration(lynched_name, lynched_role, day)
    _get_game_ref(game_id).update({"last_narration": narration})

    lynched_info = {
        "lynched": target_id,
        "lynched_name": lynched_name,
        "lynched_role": lynched_role,
        "narration": narration,
    }

    win = check_win_condition(game_id)
    if win:
        return {"action": "gameover", **win, **lynched_info}

    result = _start_new_night(game_id, game)
    result.update(lynched_info)
    return result


def _start_new_night(game_id: str, game: dict) -> dict:
    night = _get_night_number(game) + 1
    _start_phase(game_id, "night", "mafia", MAFIA_PHASE_DURATION, extra_updates={
        "night_number": night,
        "mafia_target": None,
        "doctor_target": None,
        "detective_target": None,
        "detective_result": None,
        "vote_now_presses": [],
    })
    return {"action": "night_started", "night_number": night, "duration": MAFIA_PHASE_DURATION}


# ---------------------------------------------------------------------------
# Majority Check After Each Vote  [ADDED – bug fix]
# ---------------------------------------------------------------------------

def check_and_resolve_majority(game_id: str) -> dict | None:
    """
    Called after each cast_vote. If a majority is reached, resolve lynch
    immediately and advance phase. Returns result dict or None.
    """
    game = _get_game(game_id)
    if not game or game.get("status") != "voting":
        return None

    alive = _alive_players(game)
    alive_count = len(alive)
    majority = (alive_count // 2) + 1

    votes_ref = db.collection("votes").document(game_id).collection("round_votes")
    day = _get_day_number(game)
    vote_docs = votes_ref.where("day", "==", day).stream()

    vote_counts: Counter = Counter()
    for doc in vote_docs:
        d = doc.to_dict()
        target = d.get("target")
        if target and target in alive:
            vote_counts[target] += 1

    for target, count in vote_counts.items():
        if count >= majority:
            return _lynch_player(game_id, game, target, day)

    return None


# ---------------------------------------------------------------------------
# Bot Night Actions  [ADDED]
# ---------------------------------------------------------------------------

def execute_bot_night_actions(game_id: str, game: dict, sub_phase: str):
    """
    Execute automatic night actions for all bots in the current sub-phase.
    """
    from bot_personas import generate_bot_vote as _gen_vote
    alive = _alive_players(game)
    night = _get_night_number(game)

    if sub_phase == "mafia":
        # FIX: Auto-vote for all mafia to prevent deadlock
        # Previously required is_bot check, but if host is mafia and not a bot,
        # the phase would deadlock forever. Now ALL alive mafia auto-vote.
        for pid, p in alive.items():
            if p.get("role") == "mafia":
                # Pick random alive non-mafia target
                non_mafia = [t for t, tp in alive.items() if tp.get("role") != "mafia"]
                if not non_mafia:
                    print(f"[BotNight] Mafia {pid}: no non-mafia targets, skipping")
                    continue
                target = random.choice(non_mafia)

                votes_ref = db.collection("mafia_votes").document(game_id).collection("night_votes")
                # Remove existing vote for this player/night
                existing = votes_ref.where("voter", "==", pid).where("night", "==", night).stream()
                for doc in existing:
                    doc.reference.delete()

                votes_ref.add({
                    "voter": pid,
                    "target": target,
                    "night": night,
                    "timestamp": fs.SERVER_TIMESTAMP,
                })
                print(f"Bot vote: {pid} -> {target}")  # debug

    elif sub_phase == "doctor":
        for pid, p in alive.items():
            if p.get("role") == "doctor":
                # Pick a random alive player to protect (respecting limits)
                candidates = list(alive.keys())
                random.shuffle(candidates)
                for cand in candidates:
                    allowed, _ = check_doctor_protection_limit(pid, cand, game_id)
                    if allowed:
                        record_doctor_protection(pid, cand, game_id, night)
                        _get_game_ref(game_id).update({"doctor_target": cand})
                        print(f"Bot protect: {pid} -> {cand}")  # debug
                        break

    elif sub_phase == "detective":
        for pid, p in alive.items():
            if p.get("role") == "detective":
                # Pick a random uninvestigated alive player
                candidates = [t for t in alive if t != pid]
                random.shuffle(candidates)
                for cand in candidates:
                    allowed, _ = check_detective_investigation_limit(pid, cand, game_id)
                    if allowed:
                        target_role = alive[cand].get("role", "civilian")
                        result = "guilty" if target_role == "mafia" else "innocent"
                        record_detective_investigation(pid, cand, game_id, night, result)
                        _get_game_ref(game_id).update({
                            "detective_target": cand,
                            "detective_result": result,
                        })
                        print(f"Bot investigate: {pid} -> {cand} = {result}")  # debug
                        break


# ---------------------------------------------------------------------------
# Bot Day Chat  [ADDED]
# ---------------------------------------------------------------------------

def trigger_bot_day_chat(game_id: str, game: dict) -> list[dict]:
    """
    Generate and post chat messages from alive bots during the day phase.
    Returns list of messages posted.
    """
    from bot_personas import generate_bot_chat_message

    alive = _alive_players(game)
    alive_names = {pid: p.get("name", pid) for pid, p in alive.items()}
    day = _get_day_number(game)

    # Fetch recent chat for context
    recent_docs = (
        db.collection("public_chat").document(game_id)
        .collection("messages")
        .where("day_number", "==", day)
        .order_by("timestamp")
        .limit(20)
        .stream()
    )
    recent_chat = []
    for doc in recent_docs:
        d = doc.to_dict()
        recent_chat.append({
            "sender": d.get("sender", ""),
            "sender_name": alive_names.get(d.get("sender", ""), d.get("sender", "?")),
            "text": d.get("text", ""),
        })

    # Context string
    narration = game.get("last_narration", "")
    context = f"Last narration: {narration}" if narration else ""

    posted = []
    alive_bots = [(pid, p) for pid, p in alive.items() if p.get("is_bot")]

    # Pick 1-2 random bots to speak
    speakers = random.sample(alive_bots, min(len(alive_bots), random.randint(1, 2)))

    for pid, p in speakers:
        msg = generate_bot_chat_message(
            bot_id=pid,
            bot_name=p.get("name", pid),
            bot_role=p.get("role", "civilian"),
            recent_chat=recent_chat,
            alive_player_names=alive_names,
            game_context=context,
        )

        db.collection("public_chat").document(game_id).collection("messages").add({
            "sender": pid,
            "text": msg,
            "timestamp": fs.SERVER_TIMESTAMP,
            "day_number": day,
        })

        # Update last_chat_time for the bot
        _get_game_ref(game_id).update({
            f"players.{pid}.last_chat_time": fs.SERVER_TIMESTAMP,
        })

        posted.append({"bot_id": pid, "bot_name": p.get("name", pid), "message": msg})

    return posted


# ---------------------------------------------------------------------------
# Bot Voting  [ADDED]
# ---------------------------------------------------------------------------

def cast_bot_votes(game_id: str, game: dict) -> list[dict]:
    """
    Cast votes for all alive bots during the voting phase.
    Returns list of votes cast.
    """
    from bot_personas import generate_bot_vote

    alive = _alive_players(game)
    day = _get_day_number(game)

    # Fetch day chat for heuristic voting
    chat_docs = (
        db.collection("public_chat").document(game_id)
        .collection("messages")
        .where("day_number", "==", day)
        .order_by("timestamp")
        .stream()
    )
    day_chat = [doc.to_dict() for doc in chat_docs]

    votes_cast = []
    votes_ref = db.collection("votes").document(game_id).collection("round_votes")

    for pid, p in alive.items():
        if not p.get("is_bot"):
            continue

        target = generate_bot_vote(
            bot_id=pid,
            bot_role=p.get("role", "civilian"),
            alive_players=alive,
            day_chat=day_chat,
        )

        if not target:
            continue

        # Remove existing vote for this bot/day
        existing = votes_ref.where("voter", "==", pid).where("day", "==", day).stream()
        for doc in existing:
            doc.reference.delete()

        votes_ref.add({
            "voter": pid,
            "target": target,
            "day": day,
            "timestamp": fs.SERVER_TIMESTAMP,
        })

        votes_cast.append({"bot_id": pid, "target": target})

    return votes_cast

