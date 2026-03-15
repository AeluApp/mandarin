import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../config.dart';
import '../core/error_handler.dart';

/// Derive WebSocket URL from the HTTP API_URL.
/// SECURITY: Token is NOT included in the URL (OWASP M3).
/// Auth is performed via first-message after connect.
String _wsUrl(String path) {
  var base = AppConfig.apiUrl;
  if (base.startsWith('https')) {
    base = 'wss${base.substring(5)}';
  } else if (base.startsWith('http')) {
    base = 'ws${base.substring(4)}';
  }
  return '$base$path';
}

/// WebSocket client for drill sessions with heartbeat and resume support.
///
/// Protocol mirrors the web app's WebSocket implementation:
/// - Receives: session_init, show, prompt, record_request, feedback, hint, done
/// - Sends: auth, answer, audio_data, resume, skip, hint, ping
///
/// Security (OWASP M3, NIST IA-5):
/// - Auth token sent as first message after connect (NOT in URL query params).
/// - Heartbeat ping every 15s; server must respond within 10s or connection is stale.
/// - Exponential backoff reconnect (2s, 4s, 8s, 16s, 32s) with jitter.
/// - Resume token sent on reconnect to restore session state.
/// - Message size validation (max 64KB).
class WsClient {
  static const _maxReconnectAttempts = 5;
  static const _reconnectWindow = Duration(seconds: 300);
  static const _heartbeatInterval = Duration(seconds: 15);
  static const _pongTimeout = Duration(seconds: 10);
  static const _maxMessageSize = 65536; // 64KB
  static const _resumeTokenMaxAge = Duration(minutes: 10);

  WebSocketChannel? _channel;
  String? _resumeToken;
  DateTime? _resumeTokenSetAt;
  String? _accessToken;
  int _reconnectAttempts = 0;
  DateTime? _disconnectedAt;
  Timer? _reconnectTimer;
  Timer? _heartbeatTimer;
  Timer? _pongTimer;
  final _rng = Random();

  // Observability: connection metrics.
  int totalReconnects = 0;
  int totalMessagesSent = 0;
  int totalMessagesReceived = 0;
  final StreamController<Map<String, dynamic>> _messageController =
      StreamController<Map<String, dynamic>>.broadcast();

  final StreamController<WsConnectionState> _stateController =
      StreamController<WsConnectionState>.broadcast();

  Stream<Map<String, dynamic>> get messages => _messageController.stream;
  Stream<WsConnectionState> get connectionState => _stateController.stream;

  String? get resumeToken => _resumeToken;

  void setAccessToken(String token) {
    _accessToken = token;
  }

  /// Connect to a session endpoint (e.g., /session/full or /session/mini).
  Future<void> connect(String path) async {
    _reconnectAttempts = 0;
    _disconnectedAt = null;
    await _connect(path);
  }

  Future<void> _connect(String path) async {
    _stateController.add(WsConnectionState.connecting);
    _stopHeartbeat();

    // SECURITY: No token in URL. Auth via first message.
    final url = _wsUrl(path);
    final uri = Uri.parse(url);

    try {
      _channel = WebSocketChannel.connect(uri);
      _stateController.add(WsConnectionState.connected);

      // Authenticate immediately after connect.
      _sendAuth();

      // If resuming, send resume token after auth (only if fresh).
      if (_resumeToken != null && _reconnectAttempts > 0) {
        final tokenAge = _resumeTokenSetAt != null
            ? DateTime.now().difference(_resumeTokenSetAt!)
            : _resumeTokenMaxAge;
        if (tokenAge < _resumeTokenMaxAge) {
          send({'type': 'resume', 'resume_token': _resumeToken});
        } else {
          _resumeToken = null;
          _resumeTokenSetAt = null;
        }
      }

      _startHeartbeat();

      _channel!.stream.listen(
        (data) {
          try {
            final raw = data as String;

            // SECURITY: Reject oversized messages.
            if (raw.length > _maxMessageSize) return;

            final message = jsonDecode(raw) as Map<String, dynamic>;

            // Capture resume token from session_init.
            if (message['type'] == 'session_init') {
              final token = message['resume_token'];
              if (token is String) {
                _resumeToken = token;
                _resumeTokenSetAt = DateTime.now();
              }
            }

            // Any message from server = connection alive.
            _resetPongTimer();
            _reconnectAttempts = 0;
            _disconnectedAt = null;

            totalMessagesReceived++;
            _messageController.add(message);
          } catch (e, st) {
            ErrorHandler.log('WS message decode', e, st);
            // Malformed message — skip.
          }
        },
        onDone: () => _handleDisconnect(path),
        onError: (_) => _handleDisconnect(path),
      );
    } catch (e, st) {
      ErrorHandler.log('WS connect', e, st);
      _handleDisconnect(path);
    }
  }

  /// Send authentication as first message (not in URL).
  void _sendAuth() {
    if (_accessToken != null) {
      _channel?.sink.add(jsonEncode({
        'type': 'auth',
        'token': _accessToken,
      }));
    }
  }

  void _startHeartbeat() {
    _heartbeatTimer = Timer.periodic(_heartbeatInterval, (_) {
      send({'type': 'ping'});
      _pongTimer?.cancel();
      _pongTimer = Timer(_pongTimeout, () {
        _channel?.sink.close();
      });
    });
  }

  void _resetPongTimer() {
    _pongTimer?.cancel();
  }

  void _stopHeartbeat() {
    _heartbeatTimer?.cancel();
    _pongTimer?.cancel();
  }

  void _handleDisconnect(String path) {
    _stopHeartbeat();
    _stateController.add(WsConnectionState.disconnected);
    _disconnectedAt ??= DateTime.now();

    final elapsed = DateTime.now().difference(_disconnectedAt!);
    if (_reconnectAttempts < _maxReconnectAttempts &&
        elapsed < _reconnectWindow) {
      _reconnectAttempts++;
      totalReconnects++;
      final baseDelay = Duration(seconds: 1 << _reconnectAttempts);
      final jitter = Duration(milliseconds: _rng.nextInt(1000));
      final delay = baseDelay + jitter;
      _stateController.add(WsConnectionState.reconnecting);
      _reconnectTimer?.cancel();
      _reconnectTimer = Timer(delay, () => _connect(path));
    } else {
      _stateController.add(WsConnectionState.failed);
    }
  }

  /// Send a JSON message over the WebSocket.
  void send(Map<String, dynamic> message) {
    final encoded = jsonEncode(message);
    // SECURITY: Don't send oversized messages.
    if (encoded.length > _maxMessageSize) return;
    totalMessagesSent++;
    _channel?.sink.add(encoded);
  }

  void sendAnswer(String answer) {
    // SECURITY: Limit answer length.
    final sanitized = answer.length > 500 ? answer.substring(0, 500) : answer;
    send({'type': 'answer', 'value': sanitized});
  }

  void sendSkip() {
    send({'type': 'skip'});
  }

  void sendHint() {
    send({'type': 'hint'});
  }

  void sendAudio(String base64Audio) {
    // SECURITY: Limit audio payload size (~375KB decoded).
    if (base64Audio.length > 500000) return;
    send({'type': 'audio_data', 'data': base64Audio});
  }

  void sendChoice(int index) {
    // SECURITY: Validate choice index range.
    if (index < 0 || index > 9) return;
    send({'type': 'answer', 'value': '$index'});
  }

  /// Cleanly close the connection.
  Future<void> disconnect() async {
    _stopHeartbeat();
    _reconnectTimer?.cancel();
    _resumeToken = null;
    _disconnectedAt = null;
    await _channel?.sink.close();
    _channel = null;
  }

  Future<void> dispose() async {
    _stopHeartbeat();
    _reconnectTimer?.cancel();
    _resumeToken = null;
    _disconnectedAt = null;
    try {
      await _channel?.sink.close();
    } catch (e, st) {
      ErrorHandler.log('WS dispose', e, st);
      // Best-effort cleanup.
    }
    _channel = null;
    unawaited(_messageController.close());
    unawaited(_stateController.close());
  }
}

enum WsConnectionState {
  connecting,
  connected,
  disconnected,
  reconnecting,
  failed,
}
