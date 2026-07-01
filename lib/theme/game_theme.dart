import 'package:flutter/material.dart';

class GameTheme {
  static ThemeData get darkTheme {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: const Color(0xFF0F0C1B), // Deep mysterious dark purple/black
      primaryColor: const Color(0xFFE50914), // Mafia Blood Red
      colorScheme: const ColorScheme.dark(
        primary: Color(0xFFE50914),
        secondary: Color(0xFF00E5FF), // Detective Neon Cyan
        surface: Color(0xFF1A162B), // Cards and Dialogue backgrounds
        error: Color(0xFFCF6679),
      ),
      textTheme: const TextTheme(
        headlineMedium: TextStyle(fontSize: 28, color: Colors.white, fontWeight: FontWeight.bold),
        bodyLarge: TextStyle(fontSize: 16, color: Colors.white70),
      ),
    );
  }
}