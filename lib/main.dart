import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: Scaffold(
        appBar: AppBar(title: const Text('Agentic Mafia - Firebase Test')),
        body: const Center(
          child: Text(
            'Firebase Connected! ✅',
            style: TextStyle(fontSize: 24),
          ),
        ),
      ),
    );
  }
}