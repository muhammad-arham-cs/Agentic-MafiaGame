# Agentic Mafia – Backend

Python/Flask REST API for the Agentic Mafia multiplayer game. All game state is stored in Firebase Firestore.

## Prerequisites

- Python 3.10+
- A Firebase project with Firestore enabled
- `serviceAccountKey.json` from Firebase Console → Project Settings → Service Accounts → Generate New Private Key

## Setup

```bash
# 1. Navigate to the backend folder
cd backend

# 2. Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Place your Firebase service account key
#    Copy serviceAccountKey.json into this folder (backend/)

# 5. (Optional) Configure Gemini API
#    Copy .env.example to .env and add your API key
copy .env.example .env
#    Edit .env and set GEMINI_API_KEY=your_key
```

## Running

```bash
python app.py
```

The server starts on `http://0.0.0.0:5000`. All endpoints are prefixed with `/api/`.

## API Endpoints

### Game Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/create_game` | Create a new game lobby |
| POST | `/api/join_game` | Join an existing game |
| POST | `/api/start_game` | Start the game (min 6 players) |
| GET | `/api/game_state` | Get current game state (role-masked) |
| GET | `/api/my_role` | Get your assigned role |

### Night Actions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/mafia_vote` | Mafia votes for a kill target |
| POST | `/api/doctor_protect` | Doctor protects a player |
| POST | `/api/detective_investigate` | Detective investigates a player |
| GET | `/api/detective_result` | Get investigation result |

### Day Actions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/send_public_chat` | Send a message (filtered for role reveals) |
| POST | `/api/press_vote_now` | Press the Vote Now button |

### Voting

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/cast_vote` | Cast a lynch vote |

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/send_mafia_chat` | Mafia secret chat (night only) |

### Phase Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/advance_phase` | Advance to the next game phase |
| GET | `/api/check_phase` | Check if current phase should advance |

## Architecture

```
backend/
├── app.py                  # Flask routes & API endpoints
├── firebase_init.py        # Firebase Admin SDK initialization
├── game_logic.py           # Core game logic & state machine
├── gemini_client.py        # Gemini API client with fallback
├── blocked_phrases.json    # Role-reveal filter (130+ phrases)
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
└── serviceAccountKey.json  # Firebase credentials (YOU provide this)
```

## Game Flow

```
Lobby → Night (Mafia → Doctor → Detective) → Day → Voting → Night → ...→ GameOver
```

## Firestore Collections

- `games/{gameId}` – Main game document
- `public_chat/{gameId}/messages/` – Public day chat
- `mafia_chat/{gameId}/messages/` – Mafia secret night chat
- `mafia_votes/{gameId}/night_votes/` – Mafia kill votes per night
- `votes/{gameId}/round_votes/` – Lynch votes per day
- `doctor_history/{gameId}/records/` – Doctor protection history
- `detective_history/{gameId}/records/` – Investigation history
