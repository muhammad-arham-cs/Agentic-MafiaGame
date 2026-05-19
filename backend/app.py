"""
Agentic Mafia – Flask REST API
All game state is stored in Firestore. The Flutter frontend calls these endpoints.
"""

import uuid
import time
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
from firebase_admin import firestore as fs
from firebase_init import db
import game_logic as gl
from bot_personas import fill_lobby_with_bots

app = Flask(__name__)
CORS(app)


# ===================================================================
#  Helpers
# ===================================================================

def _err(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


def _ok(data: dict | None = None):
    payload = {"success": True}
    if data:
        payload.update(data)
    return jsonify(payload), 200


# ===================================================================
#  Game Management
# ===================================================================

@app.route("/api/create_game", methods=["POST"])
def create_game():
    body = request.get_json(silent=True) or {}
    host_id = body.get("host_id")
    mode = body.get("mode", "standard")

    if not host_id:
        return _err("host_id is required")
    if mode not in ("standard", "fight_to_death"):
        return _err("mode must be 'standard' or 'fight_to_death'")

    host_name = body.get("host_name", host_id)
    game_id = uuid.uuid4().hex[:12]

    game_doc = {
        "status": "lobby",
        "mode": mode,
        "phase_start_time": None,
        "phase_duration_seconds": 0,
        "night_number": 0,
        "day_number": 0,
        "night_phase_state": None,
        "mafia_target": None,
        "doctor_target": None,
        "detective_target": None,
        "detective_result": None,
        "vote_now_presses": [],
        "vote_now_triggered": False,
        "winning_team": None,
        "last_narration": None,
        "created_at": fs.SERVER_TIMESTAMP,
        "players": {
            host_id: {
                "name": host_name,
                "role": "unassigned",
                "alive": True,
                "is_host": True,
                "is_bot": False,            # FIX: Bug 1 – ensure field exists
                "last_chat_time": None,
            }
        },
    }

    db.collection("games").document(game_id).set(game_doc)
    return _ok({"game_id": game_id})


@app.route("/api/join_game", methods=["POST"])
def join_game():
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")
    player_id = body.get("player_id")
    player_name = body.get("player_name", player_id)

    if not game_id or not player_id:
        return _err("game_id and player_id are required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)
    if game["status"] != "lobby":
        return _err("Game already started")
    if player_id in game.get("players", {}):
        return _err("Player already in game")
    if len(game.get("players", {})) >= gl.MAX_PLAYERS:
        return _err(f"Game is full (max {gl.MAX_PLAYERS} players)")

    gl._get_game_ref(game_id).update({
        f"players.{player_id}": {
            "name": player_name,
            "role": "unassigned",
            "alive": True,
            "is_host": False,
            "is_bot": False,            # FIX: Bug 1 – ensure field exists
            "last_chat_time": None,
        }
    })
    return _ok({"player_count": len(game["players"]) + 1})


@app.route("/api/start_game", methods=["POST"])
def start_game():
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")
    if not game_id:
        return _err("game_id is required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)
    if game["status"] != "lobby":
        return _err("Game already started")

    players = game.get("players", {})

    # ADDED: Auto-fill bots if lobby is below minimum
    if len(players) < gl.MIN_PLAYERS:
        added_bots = fill_lobby_with_bots(game_id, game, target_count=gl.MIN_PLAYERS)
        # Re-read game after adding bots
        game = gl._get_game(game_id)
        players = game.get("players", {})

    if len(players) < gl.MIN_PLAYERS:
        return _err(f"Need at least {gl.MIN_PLAYERS} players (currently {len(players)})")
    if len(players) > gl.MAX_PLAYERS:
        return _err(f"Too many players (max {gl.MAX_PLAYERS})")

    # Assign roles
    player_ids = list(players.keys())
    role_map = gl.assign_roles(player_ids)

    # Build update dict — also ensure is_bot field is set for all players
    updates: dict = {}
    for pid, role in role_map.items():
        updates[f"players.{pid}.role"] = role
        # ADDED: set is_bot if not already present
        if not players.get(pid, {}).get("is_bot"):
            updates[f"players.{pid}.is_bot"] = False

    updates["status"] = "night"
    updates["night_phase_state"] = "mafia"
    updates["night_number"] = 1
    updates["day_number"] = 0
    updates["phase_start_time"] = fs.SERVER_TIMESTAMP
    updates["phase_duration_seconds"] = gl.MAFIA_PHASE_DURATION

    gl._get_game_ref(game_id).update(updates)

    # ADDED: Execute bot night actions for mafia phase immediately
    game = gl._get_game(game_id)
    gl.execute_bot_night_actions(game_id, game, "mafia")

    return _ok({"assigned_roles": role_map})


@app.route("/api/game_state", methods=["GET"])
def game_state():
    game_id = request.args.get("game_id")
    player_id = request.args.get("player_id")
    if not game_id:
        return _err("game_id is required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)

    # Build safe public state
    players_public = {}
    my_role = None
    for pid, p in game.get("players", {}).items():
        players_public[pid] = {
            "name": p.get("name"),
            "alive": p.get("alive"),
            "is_host": p.get("is_host"),
            "is_bot": p.get("is_bot", False),       # ADDED
        }
        if pid == player_id:
            my_role = p.get("role")
            # Include role in this player's entry only
            players_public[pid]["role"] = my_role

    state = {
        "game_id": game_id,
        "status": game.get("status"),
        "mode": game.get("mode"),
        "night_number": game.get("night_number"),
        "day_number": game.get("day_number"),
        "night_phase_state": game.get("night_phase_state"),
        "phase_duration_seconds": game.get("phase_duration_seconds"),
        "winning_team": game.get("winning_team"),
        "last_narration": game.get("last_narration"),
        "players": players_public,
        "alive_players": gl.get_alive_player_ids(game),   # ADDED – bug fix
        "my_role": my_role,
        "vote_now_count": len(game.get("vote_now_presses", [])),
    }

    # Detective gets their result
    if my_role == "detective" and game.get("detective_result"):
        state["detective_result"] = game.get("detective_result")
        state["detective_target"] = game.get("detective_target")

    return jsonify(state), 200


@app.route("/api/my_role", methods=["GET"])
def my_role():
    game_id = request.args.get("game_id")
    player_id = request.args.get("player_id")
    if not game_id or not player_id:
        return _err("game_id and player_id are required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)

    player = game.get("players", {}).get(player_id)
    if not player:
        return _err("Player not in this game", 404)

    return _ok({"role": player.get("role")})


# ===================================================================
#  Night Actions
# ===================================================================

@app.route("/api/mafia_vote", methods=["POST"])
def mafia_vote():
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")
    player_id = body.get("player_id")
    target = body.get("target")

    if not all([game_id, player_id, target]):
        return _err("game_id, player_id, and target are required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)
    if game["status"] != "night":
        return _err("Not in night phase")
    if game.get("night_phase_state") != "mafia":
        return _err("Not in mafia sub-phase")

    player = game["players"].get(player_id, {})
    if not player.get("alive"):
        return _err("Player is not alive")
    if player.get("role") != "mafia":
        return _err("Player is not mafia")

    target_player = game["players"].get(target, {})
    if not target_player.get("alive"):
        return _err("Target is not alive")

    night = gl._get_night_number(game)
    votes_ref = db.collection("mafia_votes").document(game_id).collection("night_votes")

    # Upsert: delete existing vote for this voter/night, then add new one
    existing = votes_ref.where("voter", "==", player_id).where("night", "==", night).stream()
    for doc in existing:
        doc.reference.delete()

    votes_ref.add({
        "voter": player_id,
        "target": target,
        "night": night,
        "timestamp": fs.SERVER_TIMESTAMP,
    })

    # Check if all mafia voted → can trigger early advance
    all_voted = gl._all_mafia_voted(game_id, game)
    return _ok({"all_mafia_voted": all_voted})


@app.route("/api/doctor_protect", methods=["POST"])
def doctor_protect():
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")
    player_id = body.get("player_id")
    target = body.get("target")

    if not all([game_id, player_id, target]):
        return _err("game_id, player_id, and target are required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)
    if game["status"] != "night":
        return _err("Not in night phase")
    if game.get("night_phase_state") != "doctor":
        return _err("Not in doctor sub-phase")

    player = game["players"].get(player_id, {})
    if not player.get("alive"):
        return _err("Player is not alive")
    if player.get("role") != "doctor":
        return _err("Player is not doctor")

    target_player = game["players"].get(target, {})
    if not target_player.get("alive"):
        return _err("Target is not alive")

    # Check limits
    allowed, reason = gl.check_doctor_protection_limit(player_id, target, game_id)
    if not allowed:
        return _err(f"Protection blocked: {reason}")

    # Record and set target
    night = gl._get_night_number(game)
    gl.record_doctor_protection(player_id, target, game_id, night)
    gl._get_game_ref(game_id).update({"doctor_target": target})

    return _ok({"protected": target})


@app.route("/api/detective_investigate", methods=["POST"])
def detective_investigate():
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")
    player_id = body.get("player_id")
    target = body.get("target")

    if not all([game_id, player_id, target]):
        return _err("game_id, player_id, and target are required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)
    if game["status"] != "night":
        return _err("Not in night phase")
    if game.get("night_phase_state") != "detective":
        return _err("Not in detective sub-phase")

    player = game["players"].get(player_id, {})
    if not player.get("alive"):
        return _err("Player is not alive")
    if player.get("role") != "detective":
        return _err("Player is not detective")

    target_player = game["players"].get(target, {})
    if not target_player.get("alive"):
        return _err("Target is not alive")

    # Check limits
    allowed, reason = gl.check_detective_investigation_limit(player_id, target, game_id)
    if not allowed:
        return _err(f"Investigation blocked: {reason}")

    # Determine result
    target_role = target_player.get("role", "civilian")
    result = "guilty" if target_role == "mafia" else "innocent"

    # Record
    night = gl._get_night_number(game)
    gl.record_detective_investigation(player_id, target, game_id, night, result)
    gl._get_game_ref(game_id).update({
        "detective_target": target,
        "detective_result": result,
    })

    return _ok({"target": target, "result": result})


@app.route("/api/detective_result", methods=["GET"])
def detective_result():
    game_id = request.args.get("game_id")
    player_id = request.args.get("player_id")
    if not game_id or not player_id:
        return _err("game_id and player_id are required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)

    player = game["players"].get(player_id, {})
    if player.get("role") != "detective":
        return _err("Player is not detective")

    return _ok({
        "detective_target": game.get("detective_target"),
        "detective_result": game.get("detective_result"),
    })


# ===================================================================
#  Day Actions
# ===================================================================

@app.route("/api/send_public_chat", methods=["POST"])
def send_public_chat():
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")
    player_id = body.get("player_id")
    message = body.get("message", "").strip()

    if not all([game_id, player_id, message]):
        return _err("game_id, player_id, and message are required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)
    if game["status"] != "day":
        return _err("Chat is only allowed during the day phase")

    player = game["players"].get(player_id, {})
    if not player.get("alive"):
        return _err("Dead players cannot chat")

    # Blocked phrase check
    if gl.is_message_blocked(message):
        return _err("Message blocked: Role reveals are not allowed.")

    day = gl._get_day_number(game)

    db.collection("public_chat").document(game_id).collection("messages").add({
        "sender": player_id,
        "text": message,
        "timestamp": fs.SERVER_TIMESTAMP,
        "day_number": day,
    })

    # Update last_chat_time
    gl._get_game_ref(game_id).update({
        f"players.{player_id}.last_chat_time": fs.SERVER_TIMESTAMP,
    })

    return _ok()


@app.route("/api/press_vote_now", methods=["POST"])
def press_vote_now():
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")
    player_id = body.get("player_id")

    if not game_id or not player_id:
        return _err("game_id and player_id are required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)
    if game["status"] != "day":
        return _err("Vote Now only available during day phase")

    player = game["players"].get(player_id, {})
    if not player.get("alive"):
        return _err("Dead players cannot press Vote Now")

    presses = game.get("vote_now_presses", [])
    if player_id in presses:
        return _err("Already pressed Vote Now")

    presses.append(player_id)
    active_count = gl.get_active_player_count(game)
    threshold = (active_count // 2) + 1 if active_count > 0 else 1
    triggered = len(presses) >= threshold

    updates: dict = {
        "vote_now_presses": presses,
    }
    if triggered:
        updates["vote_now_triggered"] = True
        # ADDED: Immediately transition to voting phase  [BUG FIX]
        updates["status"] = "voting"
        updates["phase_start_time"] = fs.SERVER_TIMESTAMP
        updates["phase_duration_seconds"] = gl.VOTING_PHASE_DURATION
        updates["vote_now_triggered"] = False  # reset for next day

    gl._get_game_ref(game_id).update(updates)

    # ADDED: If triggered, cast bot votes immediately
    if triggered:
        game = gl._get_game(game_id)
        gl.cast_bot_votes(game_id, game)

    return _ok({
        "press_count": len(presses),
        "active_players": active_count,
        "threshold": threshold,
        "triggered": triggered,
    })


# ===================================================================
#  Voting Phase
# ===================================================================

@app.route("/api/cast_vote", methods=["POST"])
def cast_vote():
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")
    player_id = body.get("player_id")
    target = body.get("target")

    if not all([game_id, player_id, target]):
        return _err("game_id, player_id, and target are required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)
    if game["status"] != "voting":
        return _err("Not in voting phase")

    player = game["players"].get(player_id, {})
    if not player.get("alive"):
        return _err("Dead players cannot vote")

    target_player = game["players"].get(target, {})
    if not target_player.get("alive"):
        return _err("Cannot vote for a dead player")

    day = gl._get_day_number(game)
    votes_ref = db.collection("votes").document(game_id).collection("round_votes")

    # Upsert vote
    existing = votes_ref.where("voter", "==", player_id).where("day", "==", day).stream()
    for doc in existing:
        doc.reference.delete()

    votes_ref.add({
        "voter": player_id,
        "target": target,
        "day": day,
        "timestamp": fs.SERVER_TIMESTAMP,
    })

    # ADDED: Check for majority and resolve immediately  [BUG FIX]
    majority_result = gl.check_and_resolve_majority(game_id)
    if majority_result:
        return _ok(majority_result)

    return _ok()


# ===================================================================
#  Mafia Secret Chat
# ===================================================================

@app.route("/api/send_mafia_chat", methods=["POST"])
def send_mafia_chat():
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")
    player_id = body.get("player_id")
    message = body.get("message", "").strip()

    if not all([game_id, player_id, message]):
        return _err("game_id, player_id, and message are required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)
    if game["status"] != "night":
        return _err("Mafia chat only during night phase")

    player = game["players"].get(player_id, {})
    if not player.get("alive"):
        return _err("Dead players cannot chat")
    if player.get("role") != "mafia":
        return _err("Only mafia can use this chat")

    night = gl._get_night_number(game)
    db.collection("mafia_chat").document(game_id).collection("messages").add({
        "sender": player_id,
        "text": message,
        "timestamp": fs.SERVER_TIMESTAMP,
        "night_number": night,
    })

    return _ok()


# ===================================================================
#  Phase Advancement
# ===================================================================

@app.route("/api/advance_phase", methods=["POST"])
def advance_phase_endpoint():
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")
    force = body.get("force", False)

    if not game_id:
        return _err("game_id is required")

    result = gl.advance_phase(game_id, force=force)
    if "error" in result:
        return _err(result["error"])

    # ADDED: Trigger bot actions based on what phase we just entered
    action = result.get("action", "")
    game = gl._get_game(game_id)
    if game:
        if action == "night_doctor_phase_started":
            gl.execute_bot_night_actions(game_id, game, "doctor")
        elif action == "night_detective_phase_started":
            gl.execute_bot_night_actions(game_id, game, "detective")
        elif action == "day_started":
            gl.trigger_bot_day_chat(game_id, game)
        elif action == "voting_started":
            gl.cast_bot_votes(game_id, game)
        elif action == "night_started":
            game = gl._get_game(game_id)  # re-read after _start_new_night
            gl.execute_bot_night_actions(game_id, game, "mafia")

    return _ok(result)


@app.route("/api/check_phase", methods=["GET"])
def check_phase():
    """Lightweight poll endpoint to check if the current phase should advance."""
    game_id = request.args.get("game_id")
    if not game_id:
        return _err("game_id is required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)

    elapsed = gl._phase_elapsed(game)
    return _ok({
        "status": game.get("status"),
        "night_phase_state": game.get("night_phase_state"),
        "phase_elapsed": elapsed,
        "should_advance": elapsed or game.get("vote_now_triggered", False),
    })


# ===================================================================
#  Bot Management Endpoints  [ADDED]
# ===================================================================

@app.route("/api/fill_bots", methods=["POST"])
def fill_bots():
    """Add AI bots to fill a lobby to MIN_PLAYERS."""
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")
    target = body.get("target_count", gl.MIN_PLAYERS)

    if not game_id:
        return _err("game_id is required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)
    if game["status"] != "lobby":
        return _err("Can only add bots in lobby phase")

    added = fill_lobby_with_bots(game_id, game, target_count=target)
    return _ok({"bots_added": len(added), "bot_ids": added})


@app.route("/api/trigger_bot_chat", methods=["POST"])
def trigger_bot_chat():
    """Trigger bot chat messages during the day phase."""
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")

    if not game_id:
        return _err("game_id is required")

    game = gl._get_game(game_id)
    if not game:
        return _err("Game not found", 404)
    if game["status"] != "day":
        return _err("Bot chat only during day phase")

    posted = gl.trigger_bot_day_chat(game_id, game)
    return _ok({"messages_posted": len(posted), "messages": posted})


# ===================================================================
#  Simulation Endpoint  [ADDED]
# ===================================================================

@app.route("/api/simulate_full_game", methods=["POST"])
def simulate_full_game():
    """
    Admin endpoint: create a game with bots and run it to completion.
    Proves the filler bots and game loop work end-to-end.
    """
    body = request.get_json(silent=True) or {}
    num_players = body.get("num_players", 6)
    num_players = max(gl.MIN_PLAYERS, min(gl.MAX_PLAYERS, num_players))
    mode = body.get("mode", "standard")

    log = []

    # 1. Create game with a virtual host
    host_id = "sim_host_001"
    game_id = uuid.uuid4().hex[:12]
    game_doc = {
        "status": "lobby",
        "mode": mode,
        "phase_start_time": None,
        "phase_duration_seconds": 0,
        "night_number": 0,
        "day_number": 0,
        "night_phase_state": None,
        "mafia_target": None,
        "doctor_target": None,
        "detective_target": None,
        "detective_result": None,
        "vote_now_presses": [],
        "vote_now_triggered": False,
        "winning_team": None,
        "last_narration": None,
        "created_at": fs.SERVER_TIMESTAMP,
        "players": {
            host_id: {
                "name": "SimHost",
                "role": "unassigned",
                "alive": True,
                "is_host": True,
                "is_bot": True,
                "last_chat_time": None,
            }
        },
    }
    db.collection("games").document(game_id).set(game_doc)
    log.append(f"Created game {game_id} with mode={mode}")

    # 2. Fill with bots
    game = gl._get_game(game_id)
    added = fill_lobby_with_bots(game_id, game, target_count=num_players)
    log.append(f"Added {len(added)} bots: {added}")

    # 3. Assign roles and start
    game = gl._get_game(game_id)
    players = game.get("players", {})
    player_ids = list(players.keys())
    role_map = gl.assign_roles(player_ids)

    updates = {}
    for pid, role in role_map.items():
        updates[f"players.{pid}.role"] = role
    updates["status"] = "night"
    updates["night_phase_state"] = "mafia"
    updates["night_number"] = 1
    updates["day_number"] = 0
    updates["phase_start_time"] = fs.SERVER_TIMESTAMP
    updates["phase_duration_seconds"] = gl.MAFIA_PHASE_DURATION
    gl._get_game_ref(game_id).update(updates)

    log.append(f"Roles assigned: {role_map}")
    log.append("Game started — Night 1")

    # 4. Run game loop (max 20 iterations to prevent infinite loops)
    for iteration in range(20):
        game = gl._get_game(game_id)
        if not game or game.get("status") == "gameover":
            log.append(f"Game over! Winner: {game.get('winning_team', 'unknown')}")
            break

        status = game.get("status")
        sub_phase = game.get("night_phase_state")

        if status == "night":
            # Execute bot night actions for current sub-phase
            gl.execute_bot_night_actions(game_id, game, sub_phase)
            # Force advance
            result = gl.advance_phase(game_id, force=True)
            log.append(f"Night ({sub_phase}): {result.get('action', result)}")

            # If we moved to a new night sub-phase, trigger bots again
            new_action = result.get("action", "")
            if new_action in ("night_doctor_phase_started", "night_detective_phase_started"):
                game = gl._get_game(game_id)
                new_sub = game.get("night_phase_state", "")
                gl.execute_bot_night_actions(game_id, game, new_sub)

        elif status == "day":
            # Bots chat
            game = gl._get_game(game_id)
            posted = gl.trigger_bot_day_chat(game_id, game)
            log.append(f"Day chat: {len(posted)} bot messages")
            # Force advance to voting
            result = gl.advance_phase(game_id, force=True)
            log.append(f"Day -> {result.get('action', result)}")
            # Cast bot votes
            if result.get("action") == "voting_started":
                game = gl._get_game(game_id)
                votes = gl.cast_bot_votes(game_id, game)
                log.append(f"Bot votes cast: {len(votes)}")

        elif status == "voting":
            # Cast bot votes if not yet done
            game = gl._get_game(game_id)
            votes = gl.cast_bot_votes(game_id, game)
            log.append(f"Voting: {len(votes)} bot votes")
            # Force advance
            result = gl.advance_phase(game_id, force=True)
            log.append(f"Voting result: {result}")

            if result.get("action") == "night_started":
                game = gl._get_game(game_id)
                gl.execute_bot_night_actions(game_id, game, "mafia")

    # Final state
    game = gl._get_game(game_id)
    return _ok({
        "game_id": game_id,
        "final_status": game.get("status") if game else "unknown",
        "winning_team": game.get("winning_team") if game else None,
        "log": log,
    })


# ===================================================================
#  Entry Point
# ===================================================================

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
