import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/game_provider.dart';
import '../models/player_model.dart';
import '../widgets/chat_bubble.dart';
import '../widgets/game_animation_overlay.dart';

class GameScreen extends StatelessWidget {
  const GameScreen({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<GameProvider>(context);
    final theme = Theme.of(context);

    // If game was left, pop back to lobby
    if (provider.currentGameId == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        Navigator.of(context).pushReplacementNamed('/');
      });
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      appBar: AppBar(
        title: Text('Mafia Game: ${provider.currentGameId}'),
        backgroundColor: theme.colorScheme.surface,
        actions: [
          IconButton(
            icon: const Icon(Icons.exit_to_app, color: Colors.red),
            onPressed: () {
              _showLeaveConfirmation(context, provider);
            },
          ),
          if (provider.isHost)
            IconButton(
              icon: const Icon(Icons.skip_next, color: Colors.amber),
              tooltip: 'Force Advance Phase',
              onPressed: () => provider.advancePhase(force: true),
            ),
        ],
      ),
      body: Stack(
        children: [
          SafeArea(
            child: Column(
              children: [
                _buildHeader(provider, theme),
                Expanded(
                  child: _buildPhaseContent(context, provider, theme),
                ),
              ],
            ),
          ),
          if (provider.activeAnimation != null)
            GameAnimationOverlay(
              animationName: provider.activeAnimation!.name,
              message: provider.activeAnimation!.message,
              onComplete: () => provider.completeAnimation(),
            ),
        ],
      ),
    );
  }

  void _showLeaveConfirmation(BuildContext context, GameProvider provider) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Leave Game?'),
        content: const Text('Are you sure you want to exit to the main lobby?'),
        actions: [
          TextButton(
            child: const Text('Cancel'),
            onPressed: () => Navigator.of(ctx).pop(),
          ),
          TextButton(
            child: const Text('Leave', style: TextStyle(color: Colors.red)),
            onPressed: () {
              Navigator.of(ctx).pop();
              provider.leaveGame();
            },
          ),
        ],
      ),
    );
  }

  Widget _buildHeader(GameProvider provider, ThemeData theme) {
    final room = provider.currentRoom;
    if (room == null) return const SizedBox.shrink();

    return Container(
      padding: const EdgeInsets.all(16),
      color: theme.colorScheme.surface,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'STATUS: ${room.status.toUpperCase()}',
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Mode: ${room.mode} | Day ${room.dayNumber} | Night ${room.nightNumber}',
                    style: const TextStyle(color: Colors.grey, fontSize: 12),
                  ),
                ],
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                decoration: BoxDecoration(
                  color: theme.primaryColor.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: theme.primaryColor),
                ),
                child: Text(
                  'Timer: ${provider.remainingSeconds}s',
                  style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: theme.colorScheme.secondary.withOpacity(0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              'Your Role: ${provider.myRole.toUpperCase()} (${provider.isAlive ? "ALIVE" : "ELIMINATED"})',
              style: TextStyle(
                color: theme.colorScheme.secondary,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          if (room.lastNarration != null && room.lastNarration!.isNotEmpty) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.black38,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.white10),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Narration:',
                    style: TextStyle(color: Colors.grey, fontSize: 11, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    room.lastNarration!,
                    style: const TextStyle(fontSize: 13, fontStyle: FontStyle.italic),
                  ),
                ],
              ),
            ),
          ]
        ],
      ),
    );
  }

  Widget _buildPhaseContent(BuildContext context, GameProvider provider, ThemeData theme) {
    final status = provider.currentRoom?.status ?? 'lobby';

    switch (status) {
      case 'lobby':
        return _buildLobbyPhase(provider, theme);
      case 'night':
        return _buildNightPhase(context, provider, theme);
      case 'day':
        return _buildDayPhase(provider, theme);
      case 'voting':
        return _buildVotingPhase(provider, theme);
      case 'gameover':
      case 'game_over':
        return _buildGameOverPhase(provider, theme);
      default:
        return const Center(child: CircularProgressIndicator());
    }
  }

  // --- LOBBY PHASE ---
  Widget _buildLobbyPhase(GameProvider provider, ThemeData theme) {
    final room = provider.currentRoom;
    if (room == null) return const Center(child: CircularProgressIndicator());

    final playersList = room.players.values.toList();

    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: playersList.length,
            itemBuilder: (context, index) {
              final player = playersList[index];
              return Card(
                color: theme.colorScheme.surface,
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: player.isBot ? Colors.grey : theme.primaryColor,
                    child: Text(player.name[0].toUpperCase()),
                  ),
                  title: Text(player.name),
                  trailing: Text(player.isHost ? 'Host' : (player.isBot ? 'Bot' : 'Player')),
                ),
              );
            },
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (provider.isHost) ...[
                ElevatedButton(
                  onPressed: () => provider.fillBots(),
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.blueGrey),
                  child: const Text('Add Bots (Fill Lobby)'),
                ),
                const SizedBox(height: 8),
                ElevatedButton(
                  onPressed: () => provider.startGame(),
                  style: ElevatedButton.styleFrom(backgroundColor: theme.primaryColor),
                  child: const Text('Start Game'),
                ),
              ] else ...[
                const Card(
                  color: Colors.black26,
                  child: Padding(
                    padding: EdgeInsets.all(16.0),
                    child: Text(
                      'Waiting for host to start the game...',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontStyle: FontStyle.italic),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }

  // --- NIGHT PHASE ---
  Widget _buildNightPhase(BuildContext context, GameProvider provider, ThemeData theme) {
    final room = provider.currentRoom;
    if (room == null) return const Center(child: CircularProgressIndicator());

    final role = provider.myRole;
    final isAlive = provider.isAlive;
    final subPhase = room.nightPhaseState ?? 'mafia';

    Widget actionUI;

    if (!isAlive) {
      actionUI = const Center(
        child: Text('You are dead. Spectating the night...'),
      );
    } else if (subPhase == 'mafia') {
      if (role == 'mafia') {
        final targets = room.players.values.where((p) => p.alive && p.role != 'mafia').toList();
        actionUI = _buildTargetSelectionList(
          title: 'Select target to eliminate:',
          players: targets,
          theme: theme,
          onSelected: (targetId) => provider.mafiaVote(targetId),
        );
      } else {
        actionUI = _buildWaitingNightUI('Mafia is choosing a target...');
      }
    } else if (subPhase == 'doctor') {
      if (role == 'doctor') {
        final targets = room.players.values.where((p) => p.alive).toList();
        actionUI = _buildTargetSelectionList(
          title: 'Select player to protect:',
          players: targets,
          theme: theme,
          checkEnabled: (p) => provider.canDoctorProtect(p.id),
          onSelected: (targetId) => provider.doctorProtect(targetId),
        );
      } else {
        actionUI = _buildWaitingNightUI('Doctor is protecting a victim...');
      }
    } else if (subPhase == 'detective') {
      if (role == 'detective') {
        final targets = room.players.values.where((p) => p.alive && p.id != provider.currentPlayerId).toList();
        actionUI = _buildTargetSelectionList(
          title: 'Select target to investigate:',
          players: targets,
          theme: theme,
          checkEnabled: (p) => provider.canDetectiveInvestigate(p.id),
          onSelected: (targetId) => provider.detectiveInvestigate(targetId),
        );
      } else {
        actionUI = _buildWaitingNightUI('Detective is investigating...');
      }
    } else {
      actionUI = _buildWaitingNightUI('Night resolution finishing...');
    }

    return Column(
      children: [
        Expanded(child: actionUI),
        if (role == 'mafia') ...[
          const Divider(height: 1),
          const SizedBox(
            height: 250,
            child: ChatPanel(isMafiaOnly: true),
          ),
        ]
      ],
    );
  }

  Widget _buildWaitingNightUI(String message) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.nights_stay, size: 64, color: Colors.indigo),
          const SizedBox(height: 16),
          Text(
            message,
            style: const TextStyle(fontSize: 16, fontStyle: FontStyle.italic),
          ),
          const SizedBox(height: 16),
          const CircularProgressIndicator(),
        ],
      ),
    );
  }

  Widget _buildTargetSelectionList({
    required String title,
    required List<PlayerModel> players,
    required ThemeData theme,
    bool Function(PlayerModel)? checkEnabled,
    required ValueChanged<String> onSelected,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.all(16.0),
          child: Text(
            title,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          ),
        ),
        Expanded(
          child: ListView.builder(
            itemCount: players.length,
            itemBuilder: (context, index) {
              final player = players[index];
              final isEnabled = checkEnabled == null ? true : checkEnabled(player);

              return ListTile(
                title: Text(player.name),
                trailing: ElevatedButton(
                  onPressed: isEnabled ? () => onSelected(player.id) : null,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: theme.primaryColor,
                  ),
                  child: const Text('Select'),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  // --- DAY PHASE ---
  Widget _buildDayPhase(GameProvider provider, ThemeData theme) {
    final room = provider.currentRoom;
    if (room == null) return const Center(child: CircularProgressIndicator());

    final playersList = room.players.values.toList();

    // Calculate how many pressed vote now
    final voteNowCount = room.voteNowPresses.length;
    final activeCount = playersList.where((p) => p.alive).length;
    final threshold = (activeCount ~/ 2) + 1;

    return Column(
      children: [
        // Show status of Vote Now
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          color: Colors.amber.withOpacity(0.1),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Vote Now: $voteNowCount/$threshold presses',
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              if (provider.isAlive)
                ElevatedButton(
                  onPressed: room.voteNowPresses.contains(provider.currentPlayerId)
                      ? null
                      : () => provider.pressVoteNow(),
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.amber),
                  child: const Text('VOTE NOW'),
                ),
            ],
          ),
        ),
        Expanded(
          child: DefaultTabController(
            length: provider.myRole == 'mafia' ? 2 : 1,
            child: Column(
              children: [
                TabBar(
                  tabs: [
                    const Tab(text: 'Public Chat'),
                    if (provider.myRole == 'mafia') const Tab(text: 'Mafia Secret Chat'),
                  ],
                ),
                Expanded(
                  child: TabBarView(
                    children: [
                      ChatPanel(isMafiaOnly: false),
                      if (provider.myRole == 'mafia') ChatPanel(isMafiaOnly: true),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  // --- VOTING PHASE ---
  Widget _buildVotingPhase(GameProvider provider, ThemeData theme) {
    final room = provider.currentRoom;
    if (room == null) return const Center(child: CircularProgressIndicator());

    final alivePlayers = room.players.values.where((p) => p.alive).toList();

    return Column(
      children: [
        const Padding(
          padding: EdgeInsets.all(12.0),
          child: Text(
            'CAST YOUR LYNCH VOTE',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18, color: Colors.red),
          ),
        ),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: alivePlayers.length,
            itemBuilder: (context, index) {
              final player = alivePlayers[index];
              // Fetch vote count locally calculated from the round_votes subcollection stream
              final voteCount = provider.getVoteCountForPlayer(player.id);

              return Card(
                color: theme.colorScheme.surface,
                child: ListTile(
                  title: Text(player.name),
                  subtitle: Text('Votes: $voteCount'),
                  trailing: provider.isAlive
                      ? ElevatedButton(
                          onPressed: () => provider.castVote(player.id),
                          style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
                          child: const Text('VOTE'),
                        )
                      : null,
                ),
              );
            },
          ),
        ),
        const Divider(height: 1),
        const SizedBox(
          height: 250,
          child: ChatPanel(isMafiaOnly: false),
        ),
      ],
    );
  }

  // --- GAMEOVER PHASE ---
  Widget _buildGameOverPhase(GameProvider provider, ThemeData theme) {
    final room = provider.currentRoom;
    final winningTeam = room?.winningTeam ?? 'unknown';

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.emoji_events, size: 100, color: Colors.amber),
            const SizedBox(height: 24),
            Text(
              'GAME OVER',
              style: theme.textTheme.headlineMedium,
            ),
            const SizedBox(height: 16),
            Text(
              'WINNERS: ${winningTeam.toUpperCase()}',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: winningTeam.toLowerCase() == 'mafia' ? Colors.red : Colors.green,
              ),
            ),
            if (room?.lastNarration != null) ...[
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.white12),
                ),
                child: Text(
                  room!.lastNarration!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontStyle: FontStyle.italic),
                ),
              ),
            ],
            const SizedBox(height: 48),
            ElevatedButton(
              onPressed: () {
                provider.leaveGame();
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: theme.primaryColor,
                padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
              ),
              child: const Text('Back to Lobby'),
            ),
          ],
        ),
      ),
    );
  }
}

// --- TABBED CHAT CONTAINER ---
class ChatPanel extends StatefulWidget {
  final bool isMafiaOnly;

  const ChatPanel({Key? key, required this.isMafiaOnly}) : super(key: key);

  @override
  State<ChatPanel> createState() => _ChatPanelState();
}

class _ChatPanelState extends State<ChatPanel> {
  final TextEditingController _messageController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  void _sendMessage(GameProvider provider) {
    final text = _messageController.text.trim();
    if (text.isEmpty) return;

    if (widget.isMafiaOnly) {
      provider.sendMafiaChat(text);
    } else {
      provider.sendPublicChat(text);
    }
    _messageController.clear();
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<GameProvider>(context);
    final messages = widget.isMafiaOnly ? provider.mafiaMessages : provider.publicMessages;
    final theme = Theme.of(context);

    // Auto-scroll to bottom on new messages
    WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());

    return Container(
      color: theme.colorScheme.surface.withOpacity(0.5),
      child: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.all(8.0),
              itemCount: messages.length,
              itemBuilder: (context, index) {
                final msg = messages[index];
                final isMe = msg.sender == provider.currentPlayerId;
                final senderName = provider.currentRoom?.players[msg.sender]?.name ?? msg.sender;

                return ChatBubble(
                  message: msg.text,
                  senderName: senderName,
                  isMe: isMe,
                  isMafiaChat: widget.isMafiaOnly,
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _messageController,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      hintText: widget.isMafiaOnly ? 'Mafia Secret chat...' : 'Public discussion...',
                      hintStyle: const TextStyle(color: Colors.grey),
                      filled: true,
                      fillColor: Colors.black26,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(24),
                        borderSide: BorderSide.none,
                      ),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    ),
                    onSubmitted: (_) => _sendMessage(provider),
                  ),
                ),
                const SizedBox(width: 8),
                CircleAvatar(
                  backgroundColor: widget.isMafiaOnly ? theme.primaryColor : theme.colorScheme.secondary,
                  child: IconButton(
                    icon: const Icon(Icons.send, color: Colors.white),
                    onPressed: () => _sendMessage(provider),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
