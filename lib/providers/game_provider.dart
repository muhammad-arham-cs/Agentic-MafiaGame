import 'dart:async';
import 'package:flutter/material.dart';
import 'package:firebase_auth/firebase_auth.dart';
import '../models/player_model.dart';
import '../services/api_service.dart';
import '../services/firestore_service.dart';

class GameAnimation {
  final String name;
  final String message;
  GameAnimation(this.name, this.message);
}

class GameProvider extends ChangeNotifier {
  final ApiService _apiService = ApiService();
  final FirestoreService _firestoreService = FirestoreService();
  final FirebaseAuth _auth = FirebaseAuth.instance;

  final TextEditingController roomCodeController = TextEditingController();
  final TextEditingController playerNameController = TextEditingController();

  String currentPlayerId = '';
  String currentPlayerName = 'Player';
  String? currentGameId;
  GameRoomModel? currentRoom;

  List<ChatMessage> publicMessages = [];
  List<ChatMessage> mafiaMessages = [];
  List<Map<String, dynamic>> doctorHistory = [];
  List<Map<String, dynamic>> detectiveHistory = [];
  List<Map<String, dynamic>> roundVotes = [];

  bool isLoading = false;
  String? errorMessage;

  // Stream Subscriptions
  StreamSubscription? _roomSubscription;
  StreamSubscription? _publicChatSubscription;
  StreamSubscription? _mafiaChatSubscription;
  StreamSubscription? _doctorHistorySubscription;
  StreamSubscription? _detectiveHistorySubscription;
  StreamSubscription? _votesSubscription;

  // Animation States
  final List<GameAnimation> _animationQueue = [];
  GameAnimation? activeAnimation;

  // Prevent duplicate animations on the same phases
  int lastAnimatedNightNumber = 0;
  int lastAnimatedDayNumber = 0;
  int lastAnimatedLynchDayNumber = 0;
  int lastAnimatedDetectiveNightNumber = 0;

  Timer? _countdownTimer;

  GameProvider() {
    _signInAnonymously();
    _startLocalCountdown();
  }

  bool get isHost {
    if (currentRoom == null) return false;
    return currentRoom!.players[currentPlayerId]?.isHost ?? false;
  }

  String get myRole {
    if (currentRoom == null) return 'unassigned';
    return currentRoom!.players[currentPlayerId]?.role ?? 'unassigned';
  }

  bool get isAlive {
    if (currentRoom == null) return false;
    return currentRoom!.players[currentPlayerId]?.alive ?? false;
  }

  int get remainingSeconds {
    if (currentRoom == null || currentRoom!.phaseStartTime == null) return 0;
    final elapsed = DateTime.now().difference(currentRoom!.phaseStartTime!).inSeconds;
    final remaining = currentRoom!.phaseDurationSeconds - elapsed;
    return remaining > 0 ? remaining : 0;
  }

  Future<void> _signInAnonymously() async {
    try {
      final userCredential = await _auth.signInAnonymously();
      currentPlayerId = userCredential.user?.uid ?? '';
    } catch (e) {
      currentPlayerId = 'user_${DateTime.now().millisecondsSinceEpoch}';
      debugPrint('Firebase Auth failed, falling back to local ID: $e');
    }
    notifyListeners();
  }

  void _startLocalCountdown() {
    _countdownTimer?.cancel();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (currentRoom != null && currentRoom!.phaseStartTime != null) {
        notifyListeners();
      }
    });
  }

  void _triggerAnimation(String name, String message) {
    _animationQueue.add(GameAnimation(name, message));
    if (activeAnimation == null) {
      _playNextAnimation();
    }
  }

  void _playNextAnimation() {
    if (_animationQueue.isNotEmpty) {
      activeAnimation = _animationQueue.removeAt(0);
      notifyListeners();
    } else {
      activeAnimation = null;
      notifyListeners();
    }
  }

  void completeAnimation() {
    _playNextAnimation();
  }

  void _onRoomUpdate(GameRoomModel? newRoom) {
    if (newRoom == null) {
      currentRoom = null;
      notifyListeners();
      return;
    }

    final oldRoom = currentRoom;
    currentRoom = newRoom;

    if (oldRoom != null) {
      // 1. Entering Night Phase
      if (newRoom.status == 'night' && oldRoom.status != 'night') {
        if (newRoom.nightNumber > lastAnimatedNightNumber) {
          lastAnimatedNightNumber = newRoom.nightNumber;
          _triggerAnimation('night_eyes_close', 'Night falls. Close your eyes.');
        }
      }

      // 2. Entering Day Phase (Resolving Night)
      if (newRoom.status == 'day' && oldRoom.status == 'night') {
        if (newRoom.dayNumber > lastAnimatedDayNumber) {
          lastAnimatedDayNumber = newRoom.dayNumber;
          // Determine who died during the night
          final deadPlayers = oldRoom.alivePlayers.where((p) => !newRoom.alivePlayers.contains(p)).toList();
          if (deadPlayers.isNotEmpty) {
            final deadName = newRoom.players[deadPlayers.first]?.name ?? deadPlayers.first;
            _triggerAnimation('mafia_kill_slash', '$deadName was eliminated by the mafia!');
          } else {
            _triggerAnimation('doctor_save_glow', 'A victim was saved by the doctor!');
          }
        }
      }

      // 3. Detective Investigation result scan
      if (myRole == 'detective' && newRoom.detectiveResult != null && oldRoom.detectiveResult == null) {
        if (newRoom.nightNumber > lastAnimatedDetectiveNightNumber) {
          lastAnimatedDetectiveNightNumber = newRoom.nightNumber;
          final targetName = newRoom.players[newRoom.detectiveTarget]?.name ?? newRoom.detectiveTarget ?? '';
          final result = newRoom.detectiveResult;
          _triggerAnimation('detective_scan', 'Scan result: $targetName is $result.');
        }
      }

      // 4. Lynch resolution (Transitioning out of voting phase due to a lynch)
      if ((newRoom.status == 'night' || newRoom.status == 'gameover' || newRoom.status == 'game_over') && oldRoom.status == 'voting') {
        if (oldRoom.dayNumber > lastAnimatedLynchDayNumber) {
          lastAnimatedLynchDayNumber = oldRoom.dayNumber;
          final deadPlayers = oldRoom.alivePlayers.where((p) => !newRoom.alivePlayers.contains(p)).toList();
          if (deadPlayers.isNotEmpty) {
            final deadName = newRoom.players[deadPlayers.first]?.name ?? deadPlayers.first;
            _triggerAnimation('lynch_noose', '$deadName was lynched by the town!');
          }
        }
      }
    } else {
      // Initial load animation
      if (newRoom.status == 'night') {
        lastAnimatedNightNumber = newRoom.nightNumber;
        _triggerAnimation('night_eyes_close', 'Night falls. Close your eyes.');
      }
    }

    notifyListeners();
  }

  void _setupListeners(String gameId) {
    _cleanupListeners();

    // Listen to Game state document
    _roomSubscription = _firestoreService.getGameStream(gameId).listen((room) {
      _onRoomUpdate(room);
    });

    // Listen to Public Chat Messages
    _publicChatSubscription = _firestoreService.getPublicChatStream(gameId).listen((messages) {
      publicMessages = messages;
      notifyListeners();
    });

    // Listen to Mafia Secret Chat Messages
    _mafiaChatSubscription = _firestoreService.getMafiaChatStream(gameId).listen((messages) {
      mafiaMessages = messages;
      notifyListeners();
    });

    // Listen to Doctor's Protection History
    _doctorHistorySubscription = _firestoreService.getDoctorHistoryStream(gameId, currentPlayerId).listen((history) {
      doctorHistory = history;
      notifyListeners();
    });

    // Listen to Detective's Investigation History
    _detectiveHistorySubscription = _firestoreService.getDetectiveHistoryStream(gameId, currentPlayerId).listen((history) {
      detectiveHistory = history;
      notifyListeners();
    });

    // Listen to Round Votes
    _votesSubscription = _firestoreService.getRoundVotesStream(gameId).listen((votes) {
      roundVotes = votes;
      notifyListeners();
    });
  }

  void _cleanupListeners() {
    _roomSubscription?.cancel();
    _publicChatSubscription?.cancel();
    _mafiaChatSubscription?.cancel();
    _doctorHistorySubscription?.cancel();
    _detectiveHistorySubscription?.cancel();
    _votesSubscription?.cancel();

    publicMessages.clear();
    mafiaMessages.clear();
    doctorHistory.clear();
    detectiveHistory.clear();
    roundVotes.clear();
  }

  bool canDoctorProtect(String targetId) {
    if (targetId == currentPlayerId) {
      // Doctor can self-protect at most 1 time total
      final selfProtectCount = doctorHistory.where((r) => r['target'] == currentPlayerId).length;
      return selfProtectCount < 1;
    }
    // Doctor can protect another player at most 2 times total
    final protectCount = doctorHistory.where((r) => r['target'] == targetId).length;
    return protectCount < 2;
  }

  bool canDetectiveInvestigate(String targetId) {
    if (targetId == currentPlayerId) return false;
    // Check if target is already in the history records
    final investigated = detectiveHistory.any((r) => r['target'] == targetId);
    return !investigated;
  }

  int getVoteCountForPlayer(String playerId) {
    if (currentRoom == null) return 0;
    final currentDay = currentRoom!.dayNumber;
    return roundVotes.where((v) => v['target'] == playerId && v['day'] == currentDay).length;
  }

  // --- API Actions ---

  Future<void> createRoom({String mode = 'standard'}) async {
    isLoading = true;
    errorMessage = null;
    notifyListeners();

    try {
      final name = playerNameController.text.trim();
      if (name.isNotEmpty) {
        currentPlayerName = name;
      }

      final gameId = await _apiService.createGame(
        hostId: currentPlayerId,
        hostName: currentPlayerName,
        mode: mode,
      );

      currentGameId = gameId;
      _setupListeners(gameId);
    } catch (e) {
      errorMessage = e.toString();
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> joinRoom(String gameId) async {
    isLoading = true;
    errorMessage = null;
    notifyListeners();

    try {
      final name = playerNameController.text.trim();
      if (name.isNotEmpty) {
        currentPlayerName = name;
      }

      final success = await _apiService.joinGame(
        gameId: gameId,
        playerId: currentPlayerId,
        playerName: currentPlayerName,
      );

      if (success) {
        currentGameId = gameId;
        _setupListeners(gameId);
        return true;
      } else {
        errorMessage = 'Failed to join game';
        return false;
      }
    } catch (e) {
      errorMessage = e.toString();
      return false;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  Future<void> startGame() async {
    if (currentGameId == null) return;
    try {
      await _apiService.startGame(gameId: currentGameId!);
    } catch (e) {
      errorMessage = e.toString();
      notifyListeners();
    }
  }

  Future<void> fillBots() async {
    if (currentGameId == null) return;
    try {
      await _apiService.fillBots(gameId: currentGameId!, targetCount: 6);
    } catch (e) {
      errorMessage = e.toString();
      notifyListeners();
    }
  }

  Future<void> mafiaVote(String target) async {
    if (currentGameId == null) return;
    try {
      await _apiService.mafiaVote(
        gameId: currentGameId!,
        playerId: currentPlayerId,
        target: target,
      );
    } catch (e) {
      errorMessage = e.toString();
      notifyListeners();
    }
  }

  Future<void> doctorProtect(String target) async {
    if (currentGameId == null) return;
    try {
      await _apiService.doctorProtect(
        gameId: currentGameId!,
        playerId: currentPlayerId,
        target: target,
      );
    } catch (e) {
      errorMessage = e.toString();
      notifyListeners();
    }
  }

  Future<void> detectiveInvestigate(String target) async {
    if (currentGameId == null) return;
    try {
      await _apiService.detectiveInvestigate(
        gameId: currentGameId!,
        playerId: currentPlayerId,
        target: target,
      );
    } catch (e) {
      errorMessage = e.toString();
      notifyListeners();
    }
  }

  Future<void> sendPublicChat(String message) async {
    if (currentGameId == null || message.trim().isEmpty) return;
    try {
      await _apiService.sendPublicChat(
        gameId: currentGameId!,
        playerId: currentPlayerId,
        message: message,
      );
    } catch (e) {
      errorMessage = e.toString();
      notifyListeners();
    }
  }

  Future<void> sendMafiaChat(String message) async {
    if (currentGameId == null || message.trim().isEmpty) return;
    try {
      await _apiService.sendMafiaChat(
        gameId: currentGameId!,
        playerId: currentPlayerId,
        message: message,
      );
    } catch (e) {
      errorMessage = e.toString();
      notifyListeners();
    }
  }

  Future<void> pressVoteNow() async {
    if (currentGameId == null) return;
    try {
      await _apiService.pressVoteNow(
        gameId: currentGameId!,
        playerId: currentPlayerId,
      );
    } catch (e) {
      errorMessage = e.toString();
      notifyListeners();
    }
  }

  Future<void> castVote(String target) async {
    if (currentGameId == null) return;
    try {
      await _apiService.castVote(
        gameId: currentGameId!,
        playerId: currentPlayerId,
        target: target,
      );
    } catch (e) {
      errorMessage = e.toString();
      notifyListeners();
    }
  }

  Future<void> advancePhase({bool force = false}) async {
    if (currentGameId == null) return;
    try {
      await _apiService.advancePhase(gameId: currentGameId!, force: force);
    } catch (e) {
      errorMessage = e.toString();
      notifyListeners();
    }
  }

  void leaveGame() {
    _cleanupListeners();
    currentGameId = null;
    currentRoom = null;
    roomCodeController.clear();
    _animationQueue.clear();
    activeAnimation = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _cleanupListeners();
    _countdownTimer?.cancel();
    roomCodeController.dispose();
    playerNameController.dispose();
    super.dispose();
  }
}
