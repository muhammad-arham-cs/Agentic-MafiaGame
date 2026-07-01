import 'package:flutter/material.dart';
import 'package:lottie/lottie.dart';

class GameAnimationOverlay extends StatelessWidget {
  final String animationName; // e.g., 'mafia_kill_slash', 'night_eyes_close'
  final String message;       // Text to show on overlay
  final VoidCallback onComplete;

  const GameAnimationOverlay({
    Key? key,
    required this.animationName,
    required this.message,
    required this.onComplete,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black.withOpacity(0.85), // Dims the entire game UI behind it
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Lottie.asset(
              'assets/animations/$animationName.json',
              width: 300,
              height: 300,
              repeat: false, // Executes animation once per transition
            ),
            const SizedBox(height: 20),
            Text(
              message,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.bold,
                letterSpacing: 1.5,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 30),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: Theme.of(context).primaryColor,
              ),
              onPressed: onComplete,
              child: const Text("Continue"),
            )
          ],
        ),
      ),
    );
  }
}