# Agentic Mafia

A fully automated, real-time multiplayer social deduction game where AI runs the show.

Agentic Mafia replaces the human moderator with an AI Game Master. It manages night and day cycles, generates dramatic narrations, and fills empty lobby slots with intelligent AI bots that chat, lie, defend, and vote like real players.

## Features

- AI Host Narrator - Gemini-powered storytelling for every night kill and lynch
- AI Filler Bots - Bots with unique personalities chat and vote strategically
- Real-time Multiplayer - Instant game state sync via Firebase Firestore
- Full Role System - Mafia, Detective, Doctor, and Civilians with special night actions
- Smart Chat Filter - Blocks role reveals in English and Roman Urdu while allowing deception
- Lottie Animations - Smooth visual effects for kills, saves, investigations, and lynches
- Fight to Death Mode - The game continues until one side is completely eliminated

## Architecture

Flutter Mobile App communicates with Firebase Firestore, which communicates with the Python Flask Backend. The backend calls the Gemini API for AI features.

The backend owns all game logic and AI. The Flutter app listens to Firestore for real-time updates and calls REST endpoints for player actions.

## Tech Stack

- Mobile App: Flutter, Dart, Provider, Lottie
- Backend: Python, Flask, Firebase Admin SDK
- Database: Firebase Firestore
- AI: Google Gemini (gemini-2.5-flash)
- Authentication: Firebase Anonymous Auth

## Project Structure

- backend/
  - app.py - REST API endpoints
  - game_logic.py - Core game state machine
  - gemini_client.py - Gemini API wrapper
  - bot_personas.py - AI bot personas
  - firebase_init.py - Firebase Admin SDK init
  - blocked_phrases.json - Chat filter list
  - requirements.txt - Python dependencies
  - .env.example - Environment variables template
- lib/
  - main.dart - App entry point
  - screens/ - Splash, Lobby, Game screens
  - services/ - API and Firestore services
  - providers/ - State management
  - models/ - Player and game models
  - theme/ - Dark game theme
  - widgets/ - Chat bubble, Animation overlay
- assets/animations/ - Lottie JSON files
- pubspec.yaml - Flutter dependencies
- README.md

## Quick Start

### Backend

Go to the backend folder:

```
cd backend
pip install -r requirements.txt
```

Place your `serviceAccountKey.json` and `.env` (with Gemini API key) inside the `backend/` folder.

Run the server:

```
python -c "from app import app; app.run(debug=False, host='0.0.0.0', port=5000)"
```

### Flutter App

Install dependencies and launch:

```
flutter pub get
flutter run -d <device-id>
```

For a physical device, first forward the backend port:

```
adb reverse tcp:5000 tcp:5000
```

Then change the API base URL in `lib/services/api_service.dart` from `10.0.2.2` to `localhost`.

## How It Plays

1. Join or create a lobby - fill with bots if needed.
2. Night: Mafia choose a target, Doctor protects, Detective investigates.
3. Day: Discuss in public chat, press Vote Now to trigger early voting.
4. Voting: Lynch the most suspected player.
5. The cycle repeats until one team is eliminated.
