import 'package:flutter/material.dart';

class ChatBubble extends StatelessWidget {
  final String message;
  final String senderName;
  final bool isMe;
  final bool isMafiaChat; // If true, rendering will adjust to blood-red outlines for secret chat

  const ChatBubble({
    Key? key,
    required this.message,
    required this.senderName,
    required this.isMe,
    this.isMafiaChat = false,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6.0, horizontal: 12.0),
      child: Column(
        crossAxisAlignment: isMe ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          Text(
            senderName,
            style: TextStyle(fontSize: 12, color: isMafiaChat ? theme.primaryColor : Colors.grey),
          ),
          const SizedBox(height: 3),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: isMe 
                  ? (isMafiaChat ? theme.primaryColor.withOpacity(0.3) : theme.colorScheme.secondary.withOpacity(0.2))
                  : theme.colorScheme.surface,
              border: isMafiaChat ? Border.all(color: theme.primaryColor, width: 1.5) : null,
              borderRadius: BorderRadius.only(
                topLeft: const Radius.circular(12),
                topRight: const Radius.circular(12),
                bottomLeft: Radius.circular(isMe ? 12 : 0),
                bottomRight: Radius.circular(isMe ? 0 : 12),
              ),
            ),
            child: Text(
              message,
              style: const TextStyle(color: Colors.white, fontSize: 15),
            ),
          ),
        ],
      ),
    );
  }
}