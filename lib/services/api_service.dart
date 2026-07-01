import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  final String baseUrl;

  ApiService({this.baseUrl = 'http://localhost:5000/api'});

  Future<Map<String, dynamic>> _post(String endpoint, Map<String, dynamic> body) async {
    final uri = Uri.parse('$baseUrl$endpoint');
    final response = await http.post(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );

    final responseBody = jsonDecode(response.body);
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return responseBody as Map<String, dynamic>;
    } else {
      throw Exception(responseBody['error'] ?? 'Server error ${response.statusCode}');
    }
  }

  Future<Map<String, dynamic>> _get(String endpoint, Map<String, String> queryParams) async {
    final uri = Uri.parse('$baseUrl$endpoint').replace(queryParameters: queryParams);
    final response = await http.get(uri);

    final responseBody = jsonDecode(response.body);
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return responseBody as Map<String, dynamic>;
    } else {
      throw Exception(responseBody['error'] ?? 'Server error ${response.statusCode}');
    }
  }

  Future<String> createGame({required String hostId, required String hostName, String mode = 'standard'}) async {
    final result = await _post('/create_game', {
      'host_id': hostId,
      'host_name': hostName,
      'mode': mode,
    });
    return result['game_id'];
  }

  Future<bool> joinGame({required String gameId, required String playerId, required String playerName}) async {
    final result = await _post('/join_game', {
      'game_id': gameId,
      'player_id': playerId,
      'player_name': playerName,
    });
    return result['success'] ?? false;
  }

  Future<Map<String, dynamic>> startGame({required String gameId}) async {
    return await _post('/start_game', {
      'game_id': gameId,
    });
  }

  Future<Map<String, dynamic>> getGameState({required String gameId, required String playerId}) async {
    return await _get('/game_state', {
      'game_id': gameId,
      'player_id': playerId,
    });
  }

  Future<Map<String, dynamic>> advancePhase({required String gameId, bool force = false}) async {
    return await _post('/advance_phase', {
      'game_id': gameId,
      'force': force,
    });
  }

  Future<Map<String, dynamic>> fillBots({required String gameId, int targetCount = 6}) async {
    return await _post('/fill_bots', {
      'game_id': gameId,
      'target_count': targetCount,
    });
  }

  Future<bool> mafiaVote({required String gameId, required String playerId, required String target}) async {
    final result = await _post('/mafia_vote', {
      'game_id': gameId,
      'player_id': playerId,
      'target': target,
    });
    return result['all_mafia_voted'] ?? false;
  }

  Future<String> doctorProtect({required String gameId, required String playerId, required String target}) async {
    final result = await _post('/doctor_protect', {
      'game_id': gameId,
      'player_id': playerId,
      'target': target,
    });
    return result['protected'] ?? '';
  }

  Future<Map<String, dynamic>> detectiveInvestigate({required String gameId, required String playerId, required String target}) async {
    return await _post('/detective_investigate', {
      'game_id': gameId,
      'player_id': playerId,
      'target': target,
    });
  }

  Future<void> sendPublicChat({required String gameId, required String playerId, required String message}) async {
    await _post('/send_public_chat', {
      'game_id': gameId,
      'player_id': playerId,
      'message': message,
    });
  }

  Future<void> sendMafiaChat({required String gameId, required String playerId, required String message}) async {
    await _post('/send_mafia_chat', {
      'game_id': gameId,
      'player_id': playerId,
      'message': message,
    });
  }

  Future<Map<String, dynamic>> pressVoteNow({required String gameId, required String playerId}) async {
    return await _post('/press_vote_now', {
      'game_id': gameId,
      'player_id': playerId,
    });
  }

  Future<Map<String, dynamic>> castVote({required String gameId, required String playerId, required String target}) async {
    return await _post('/cast_vote', {
      'game_id': gameId,
      'player_id': playerId,
      'target': target,
    });
  }
}
