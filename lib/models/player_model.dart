class PlayerModel {
  final String id;
  final String name;
  final String role;
  final bool alive;
  final bool isHost;
  final bool isBot;
  final DateTime? lastChatTime;

  PlayerModel({
    required this.id,
    required this.name,
    required this.role,
    required this.alive,
    required this.isHost,
    required this.isBot,
    this.lastChatTime,
  });

  factory PlayerModel.fromMap(String id, Map<String, dynamic> map) {
    DateTime? chatTime;
    final lct = map['last_chat_time'];
    if (lct != null) {
      if (lct is DateTime) {
        chatTime = lct;
      } else {
        // Handle firestore Timestamp conversion in client code
        // Timestamp is converted to DateTime or handled by Firebase SDK
        chatTime = DateTime.tryParse(lct.toString());
      }
    }

    return PlayerModel(
      id: id,
      name: map['name'] ?? id,
      role: map['role'] ?? 'unassigned',
      alive: map['alive'] ?? true,
      isHost: map['is_host'] ?? false,
      isBot: map['is_bot'] ?? false,
      lastChatTime: chatTime,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'name': name,
      'role': role,
      'alive': alive,
      'is_host': isHost,
      'is_bot': isBot,
      'last_chat_time': lastChatTime?.toIso8601String(),
    };
  }
}

class GameRoomModel {
  final String gameId;
  final String status;
  final String mode;
  final DateTime? phaseStartTime;
  final int phaseDurationSeconds;
  final int nightNumber;
  final int dayNumber;
  final String? nightPhaseState;
  final String? mafiaTarget;
  final String? doctorTarget;
  final String? detectiveTarget;
  final String? detectiveResult;
  final List<String> voteNowPresses;
  final bool voteNowTriggered;
  final String? winningTeam;
  final String? lastNarration;
  final Map<String, PlayerModel> players;
  final List<String> alivePlayers;

  GameRoomModel({
    required this.gameId,
    required this.status,
    required this.mode,
    this.phaseStartTime,
    required this.phaseDurationSeconds,
    required this.nightNumber,
    required this.dayNumber,
    this.nightPhaseState,
    this.mafiaTarget,
    this.doctorTarget,
    this.detectiveTarget,
    this.detectiveResult,
    required this.voteNowPresses,
    required this.voteNowTriggered,
    this.winningTeam,
    this.lastNarration,
    required this.players,
    required this.alivePlayers,
  });

  factory GameRoomModel.fromMap(String gameId, Map<String, dynamic> map) {
    final playersMap = <String, PlayerModel>{};
    if (map['players'] != null && map['players'] is Map) {
      final pMap = map['players'] as Map<String, dynamic>;
      pMap.forEach((key, value) {
        if (value is Map<String, dynamic>) {
          playersMap[key] = PlayerModel.fromMap(key, value);
        }
      });
    }

    final List<String> aliveList = [];
    if (map['alive_players'] != null && map['alive_players'] is List) {
      aliveList.addAll(List<String>.from(map['alive_players']));
    } else {
      // Fallback: build from playersMap
      playersMap.forEach((key, p) {
        if (p.alive) {
          aliveList.add(key);
        }
      });
    }

    DateTime? startTime;
    final pst = map['phase_start_time'];
    if (pst != null) {
      if (pst is DateTime) {
        startTime = pst;
      } else {
        // Can be a firestore Timestamp or String depending on API vs Listener
        startTime = DateTime.tryParse(pst.toString());
      }
    }

    final presses = <String>[];
    if (map['vote_now_presses'] != null) {
      presses.addAll(List<String>.from(map['vote_now_presses']));
    }

    return GameRoomModel(
      gameId: gameId,
      status: map['status'] ?? 'lobby',
      mode: map['mode'] ?? 'standard',
      phaseStartTime: startTime,
      phaseDurationSeconds: map['phase_duration_seconds'] ?? 0,
      nightNumber: map['night_number'] ?? 0,
      dayNumber: map['day_number'] ?? 0,
      nightPhaseState: map['night_phase_state'],
      mafiaTarget: map['mafia_target'],
      doctorTarget: map['doctor_target'],
      detectiveTarget: map['detective_target'],
      detectiveResult: map['detective_result'],
      voteNowPresses: presses,
      voteNowTriggered: map['vote_now_triggered'] ?? false,
      winningTeam: map['winning_team'],
      lastNarration: map['last_narration'],
      players: playersMap,
      alivePlayers: aliveList,
    );
  }
}
