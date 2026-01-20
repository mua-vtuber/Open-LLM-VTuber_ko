# Chat Monitor System

A real-time chat monitoring system for YouTube and Chzzk (치지직) live streaming platforms, integrated with the Open-LLM-VTuber conversation system.

## Features

- **Multi-platform Support**: Monitor YouTube and Chzzk live chats simultaneously
- **Real-time Integration**: Chat messages are automatically injected into the conversation system
- **Automatic Reconnection**: Handles disconnections with configurable retry logic
- **Type-safe Configuration**: Fully typed configuration using Pydantic models
- **Async Architecture**: Non-blocking async operations for efficient monitoring

## Architecture

### Components

1. **ChatMonitorInterface** (`chat_monitor_interface.py`)
   - Base interface for all chat monitors
   - Defines standard message format across platforms
   - Provides common functionality for reconnection and error handling

2. **YouTubeChatMonitor** (`youtube_chat_monitor.py`)
   - Monitors YouTube live chat using YouTube Data API v3
   - Polling-based approach (checks every 2 seconds as recommended by YouTube)
   - Handles API rate limits and authentication errors

3. **ChzzkChatMonitor** (`chzzk_chat_monitor.py`)
   - Monitors Chzzk (치지직) live chat using official chzzkpy v2 API
   - WebSocket-based real-time communication
   - OAuth2 authentication with automatic token refresh
   - **Requires Python 3.11+**

4. **ChzzkOAuthManager** (`chzzk_oauth_manager.py`)
   - Handles OAuth2 authentication flow for Chzzk
   - Token storage and automatic refresh
   - Authorization URL generation and code exchange

5. **ChatMonitorManager** (`chat_monitor_manager.py`)
   - Coordinates multiple platform monitors
   - Manages lifecycle (initialization, start, stop)
   - Routes messages to conversation system
   - Provides status reporting

## Installation

### Required Dependencies

YouTube monitoring requires no additional dependencies (uses built-in httpx).

### Optional: Chzzk Support

For Chzzk monitoring, install the optional dependency:

```bash
# Python 3.11+ required
uv sync --extra chat_monitor
```

Or manually:

```bash
pip install "chzzkpy>=2.0.0"
```

## Configuration

Edit `conf.yaml` to configure chat monitoring:

```yaml
live_config:
  chat_monitor:
    # Enable/disable chat monitoring system
    enabled: true

    # YouTube Live Chat Configuration
    youtube:
      enabled: true
      # Get API key from https://console.cloud.google.com/
      api_key: "YOUR_YOUTUBE_API_KEY"
      channel_id: "YOUR_YOUTUBE_CHANNEL_ID"

    # Chzzk (치지직) Live Chat Configuration (OAuth2)
    chzzk:
      enabled: true
      channel_id: "YOUR_CHZZK_CHANNEL_ID"
      # OAuth2 credentials from CHZZK Developer Center
      client_id: "YOUR_CLIENT_ID"
      client_secret: "YOUR_CLIENT_SECRET"
      redirect_uri: "http://localhost:12393/chzzk/callback"
      # These will be automatically set after authorization
      access_token: ""
      refresh_token: ""

    # Connection retry settings
    max_retries: 10        # Maximum retry attempts
    retry_interval: 60     # Retry interval in seconds
```

### Getting YouTube API Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable "YouTube Data API v3"
4. Create credentials (API Key)
5. Copy the API key to `conf.yaml`

### Finding Your YouTube Channel ID

1. Go to your YouTube channel
2. Click on your profile picture → "Settings"
3. Click "Advanced settings"
4. Copy the "Channel ID"

### Finding Your Chzzk Channel ID

1. Go to your Chzzk channel page
2. The channel ID is in the URL: `https://chzzk.naver.com/live/{CHANNEL_ID}`

### Setting Up Chzzk OAuth Authentication

Chzzk chat monitoring requires OAuth2 authentication:

1. **Create OAuth Application**
   - Go to [CHZZK Developer Center](https://developers.chzzk.naver.com/application/)
   - Create a new OAuth application
   - Set the redirect URI to: `http://localhost:12393/chzzk/callback`
   - Copy the Client ID and Client Secret

2. **Configure `conf.yaml`**
   ```yaml
   live_config:
     chat_monitor:
       enabled: true
       chzzk:
         enabled: true
         channel_id: "YOUR_CHZZK_CHANNEL_ID"
         client_id: "YOUR_CLIENT_ID"
         client_secret: "YOUR_CLIENT_SECRET"
         redirect_uri: "http://localhost:12393/chzzk/callback"
   ```

3. **Authorize the Application**
   - Start the Open-LLM-VTuber server: `uv run run_server.py`
   - Visit `http://localhost:12393/chzzk/auth` in your browser
   - Log in to your Chzzk account and grant permissions
   - You'll be redirected back and tokens will be saved automatically
   - Tokens are stored in `cache/chzzk_tokens.json`

4. **Start Streaming**
   - Restart the server if needed
   - Start your Chzzk live stream
   - Chat monitoring will start automatically

**Note**: If tokens expire, simply visit `/chzzk/auth` again to re-authenticate.

## Usage

### Automatic Start

If configured properly, chat monitoring starts automatically when the server starts:

```bash
uv run run_server.py
```

### Manual Control via WebSocket

You can control chat monitoring through WebSocket messages:

#### Start Monitoring

```json
{
  "type": "start-chat-monitor"
}
```

Response:
```json
{
  "type": "chat-monitor-started",
  "success": true,
  "status": {
    "youtube": true,
    "chzzk": false
  }
}
```

#### Stop Monitoring

```json
{
  "type": "stop-chat-monitor"
}
```

Response:
```json
{
  "type": "chat-monitor-stopped",
  "success": true
}
```

#### Get Status

```json
{
  "type": "chat-monitor-status"
}
```

Response:
```json
{
  "type": "chat-monitor-status",
  "enabled": true,
  "running": true,
  "platforms": {
    "youtube": true,
    "chzzk": false
  }
}
```

## How It Works

### Message Flow

1. **Chat Message Received**
   - YouTube: Polled every 2 seconds via YouTube Data API
   - Chzzk: Real-time via WebSocket connection

2. **Message Processing**
   - Message is standardized into `ChatMessage` format
   - Platform-specific fields are normalized

3. **Message Broadcasting**
   - Message is broadcast to all connected WebSocket clients
   - Message format: `"[PLATFORM Chat] Author: message"`

4. **AI Response**
   - Message is injected as text-input to conversation system
   - LLM processes the message and generates response
   - Response is synthesized via TTS and played through Live2D

### ChatMessage Format

```python
{
    'platform': 'youtube' | 'chzzk',
    'author': 'Username',
    'message': 'Chat message content',
    'timestamp': '2024-01-20T12:00:00',
    'user_id': 'platform-specific-id',
    'is_moderator': False,
    'is_owner': False,
    'is_member': False,
    'badges': {}
}
```

## Error Handling

### Automatic Reconnection

- If connection is lost, the monitor automatically attempts to reconnect
- Configurable `max_retries` and `retry_interval`
- Exponential backoff can be implemented by adjusting retry logic

### Common Issues

#### YouTube API Quota Exceeded

**Symptom**: HTTP 403 errors from YouTube API

**Solution**:
- YouTube Data API has daily quota limits
- Wait until quota resets (midnight Pacific Time)
- Or request quota increase from Google Cloud Console

#### Chzzk Connection Failed

**Symptom**: Python version error or import error

**Solution**:
- Ensure Python 3.11+ is installed
- Install chzzkpy: `uv sync --extra chat_monitor`

#### No Messages Received

**Symptom**: Monitor is connected but no messages appear

**Solution**:
- Verify channel IDs are correct
- Ensure live stream is actually active
- Check API keys and credentials

## Development

### Adding a New Platform

To add support for a new streaming platform:

1. Create a new monitor class inheriting from `ChatMonitorInterface`
2. Implement required methods: `start_monitoring()`, `stop_monitoring()`, `is_connected()`
3. Add configuration class in `config_manager/live.py`
4. Update `ChatMonitorManager` to instantiate the new monitor
5. Add configuration to `conf.yaml`

Example:

```python
from .chat_monitor_interface import ChatMonitorInterface, ChatMessage

class NewPlatformMonitor(ChatMonitorInterface):
    async def start_monitoring(self) -> bool:
        # Implementation
        pass

    async def stop_monitoring(self) -> None:
        # Implementation
        pass

    def is_connected(self) -> bool:
        # Implementation
        pass
```

### Testing

To test the chat monitor without a live stream:

1. Use the WebSocket test client
2. Send mock messages via the message callback
3. Verify message format and routing

## Troubleshooting

### Enable Debug Logging

Add `--verbose` flag when running the server:

```bash
uv run run_server.py --verbose
```

### Check Monitor Status

Send a status request via WebSocket to see which monitors are connected:

```json
{
  "type": "chat-monitor-status"
}
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Python 3.11+ required` | Using Python < 3.11 with Chzzk | Upgrade Python or disable Chzzk |
| `Failed to import chzzkpy` | chzzkpy not installed | Run `uv sync --extra chat_monitor` |
| `No active live stream found` | Channel is not live | Start a live stream on the platform |
| `HTTP 403` from YouTube | API quota exceeded | Wait for quota reset or increase quota |

## Future Enhancements

- [ ] Message filtering (ignore bots, spam, etc.)
- [ ] Rate limiting (prevent AI spam from too many messages)
- [ ] Custom message formatting per platform
- [ ] Support for Super Chat / donations
- [ ] Twitch platform support
- [ ] Discord integration
- [ ] Custom callbacks for different message types

## Contributing

When contributing to the chat monitor system:

1. Follow the existing code style (use `ruff format`)
2. Add type hints to all functions
3. Write docstrings for public methods
4. Update this README if adding new features
5. Test with both YouTube and Chzzk platforms if possible

## License

Part of Open-LLM-VTuber project. See main LICENSE file for details.
