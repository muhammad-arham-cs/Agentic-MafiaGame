import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/player_model.dart';

class ChatMessage {
  final String id;
  final String sender;
  final String text;
  final DateTime? timestamp;
  final int? phaseNumber; // day_number or night_number

  ChatMessage({
    required this.id,
    required this.sender,
    required this.text,
    this.timestamp,
    this.phaseNumber,
  });

  factory ChatMessage.fromMap(String id, Map<String, dynamic> map) {
    DateTime? ts;
    final timestampField = map['timestamp'];
    if (timestampField != null) {
      if (timestampField is Timestamp) {
        ts = timestampField.toDate();
      } else if (timestampField is String) {
        ts = DateTime.tryParse(timestampField);
      }
    }
    return ChatMessage(
      id: id,
      sender: map['sender'] ?? 'unknown',
      text: map['text'] ?? '',
      timestamp: ts,
      phaseNumber: map['day_number'] ?? map['night_number'],
    );
  }
}

class FirestoreService {
  final FirebaseFirestore _db = FirebaseFirestore.instance;

  // Stream of Game Room state
  Stream<GameRoomModel?> getGameStream(String gameId) {
    return _db.collection('games').doc(gameId).snapshots().map((snapshot) {
      if (!snapshot.exists || snapshot.data() == null) {
        return null;
      }
      return GameRoomModel.fromMap(gameId, snapshot.data()!);
    });
  }

  // Stream of Public Chat Messages
  Stream<List<ChatMessage>> getPublicChatStream(String gameId) {
    return _db
        .collection('public_chat')
        .doc(gameId)
        .collection('messages')
        .orderBy('timestamp', descending: false)
        .snapshots()
        .map((snapshot) {
      return snapshot.docs.map((doc) {
        return ChatMessage.fromMap(doc.id, doc.data());
      }).toList();
    });
  }

  // Stream of Mafia Secret Chat Messages
  Stream<List<ChatMessage>> getMafiaChatStream(String gameId) {
    return _db
        .collection('mafia_chat')
        .doc(gameId)
        .collection('messages')
        .orderBy('timestamp', descending: false)
        .snapshots()
        .map((snapshot) {
      return snapshot.docs.map((doc) {
        return ChatMessage.fromMap(doc.id, doc.data());
      }).toList();
    });
  }

  // Stream doctor history records to allow the client to count protections
  Stream<List<Map<String, dynamic>>> getDoctorHistoryStream(String gameId, String doctorId) {
    return _db
        .collection('doctor_history')
        .doc(gameId)
        .collection('records')
        .where('protected_by', isEqualTo: doctorId)
        .snapshots()
        .map((snapshot) {
      return snapshot.docs.map((doc) => doc.data()).toList();
    });
  }

  // Stream detective history records to check already investigated players
  Stream<List<Map<String, dynamic>>> getDetectiveHistoryStream(String gameId, String detectiveId) {
    return _db
        .collection('detective_history')
        .doc(gameId)
        .collection('records')
        .where('investigated_by', isEqualTo: detectiveId)
        .snapshots()
        .map((snapshot) {
      return snapshot.docs.map((doc) => doc.data()).toList();
    });
  }

  // Stream round votes records to tally lynch votes
  Stream<List<Map<String, dynamic>>> getRoundVotesStream(String gameId) {
    return _db
        .collection('votes')
        .doc(gameId)
        .collection('round_votes')
        .snapshots()
        .map((snapshot) {
      return snapshot.docs.map((doc) => doc.data()).toList();
    });
  }
}
