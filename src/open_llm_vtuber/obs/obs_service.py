"""
OBS WebSocket integration service.

Connects to OBS Studio via obsws-python to read scene layout information
(source positions/sizes) and provides layout polling for broadcasting
to frontend clients.
"""

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from loguru import logger

try:
    import obsws_python as obs

    OBS_AVAILABLE = True
except ImportError:
    OBS_AVAILABLE = False
    logger.warning(
        "obsws-python not installed. OBS integration will not be available. "
        "Install with: pip install obsws-python"
    )


@dataclass
class LayoutRegion:
    """A named region in the OBS scene layout, with normalized coordinates."""

    name: str  # Region name without brackets, e.g. "character", "game", "chat"
    x: float  # 0.0~1.0 normalized horizontal position
    y: float  # 0.0~1.0 normalized vertical position
    width: float  # 0.0~1.0 normalized width
    height: float  # 0.0~1.0 normalized height

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LayoutRegion):
            return NotImplemented
        return (
            self.name == other.name
            and abs(self.x - other.x) < 1e-6
            and abs(self.y - other.y) < 1e-6
            and abs(self.width - other.width) < 1e-6
            and abs(self.height - other.height) < 1e-6
        )


@dataclass
class SceneLayout:
    """Complete scene layout with all detected regions."""

    regions: list[LayoutRegion] = field(default_factory=list)
    canvas_width: int = 1920
    canvas_height: int = 1080
    timestamp: float = field(default_factory=time.time)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SceneLayout):
            return NotImplemented
        if len(self.regions) != len(other.regions):
            return False
        return all(a == b for a, b in zip(self.regions, other.regions))


# Regex pattern for bracketed source names: [name]
_BRACKET_PATTERN = re.compile(r"^\[(.+?)\]$")


class OBSService:
    """
    Service for interacting with OBS Studio via WebSocket.

    Provides:
    - Connection management to OBS WebSocket server
    - Scene layout reading with normalized coordinates
    - Periodic layout polling with change detection
    - Screenshot capture placeholder for future vision features
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 4455,
        password: str = "",
        timeout: int = 5,
    ):
        self._host = host
        self._port = port
        self._password = password
        self._timeout = timeout
        self._client: Optional[object] = None
        self._connected = False
        self._polling_task: Optional[asyncio.Task] = None

    @property
    def is_connected(self) -> bool:
        """Whether the service is currently connected to OBS."""
        return self._connected

    def connect(self) -> bool:
        """
        Connect to OBS WebSocket server.

        Returns:
            True if connection successful, False otherwise.
        """
        if not OBS_AVAILABLE:
            logger.error("obsws-python is not installed. Cannot connect to OBS.")
            return False

        try:
            self._client = obs.ReqClient(
                host=self._host,
                port=self._port,
                password=self._password,
                timeout=self._timeout,
            )
            self._connected = True
            logger.info(f"Connected to OBS WebSocket at {self._host}:{self._port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to OBS WebSocket: {e}")
            self._connected = False
            self._client = None
            return False

    def disconnect(self) -> None:
        """Disconnect from OBS WebSocket server."""
        self.stop_layout_polling()
        if self._client is not None:
            try:
                self._client.base_client.ws.close()
            except Exception:
                pass
            self._client = None
        self._connected = False
        logger.info("Disconnected from OBS WebSocket")

    def get_layout(self) -> Optional[SceneLayout]:
        """
        Get the current scene layout from OBS.

        Reads the current scene, finds sources whose names are wrapped in
        brackets (e.g. [character], [game]), and returns their normalized
        positions and sizes.

        Returns:
            SceneLayout with detected regions, or None on failure.
        """
        if not self._connected or self._client is None:
            return None

        try:
            return self._get_layout_sync()
        except Exception as e:
            logger.error(f"Error getting OBS layout: {e}")
            self._handle_connection_error(e)
            return None

    def _get_layout_sync(self) -> Optional[SceneLayout]:
        """Synchronous implementation of layout fetching."""
        client = self._client
        if client is None:
            return None

        # Get canvas resolution
        video_settings = client.get_video_settings()
        canvas_width = video_settings.base_width
        canvas_height = video_settings.base_height

        if canvas_width <= 0 or canvas_height <= 0:
            logger.warning(f"Invalid canvas size: {canvas_width}x{canvas_height}")
            return None

        # Get current scene name
        current_scene = client.get_current_program_scene()
        scene_name = current_scene.scene_name

        # Get all scene items
        scene_items_response = client.get_scene_item_list(scene_name)
        items = scene_items_response.scene_items

        regions: list[LayoutRegion] = []

        for item in items:
            source_name = item.get("sourceName", "")
            match = _BRACKET_PATTERN.match(source_name)
            if not match:
                continue

            region_name = match.group(1)
            item_id = item.get("sceneItemId")
            if item_id is None:
                continue

            try:
                transform_response = client.get_scene_item_transform(
                    scene_name, item_id
                )
                t = transform_response.scene_item_transform

                pos_x = t.get("positionX", 0.0)
                pos_y = t.get("positionY", 0.0)

                # Use width/height from transform (includes scaling)
                width = t.get("width", 0.0)
                height = t.get("height", 0.0)

                # If width/height are 0, fall back to source dimensions * scale
                if width == 0 or height == 0:
                    source_w = t.get("sourceWidth", 0.0)
                    source_h = t.get("sourceHeight", 0.0)
                    scale_x = t.get("scaleX", 1.0)
                    scale_y = t.get("scaleY", 1.0)
                    width = source_w * scale_x
                    height = source_h * scale_y

                # Normalize to 0.0~1.0
                norm_x = pos_x / canvas_width
                norm_y = pos_y / canvas_height
                norm_w = width / canvas_width
                norm_h = height / canvas_height

                # Clamp to valid range
                norm_x = max(0.0, min(1.0, norm_x))
                norm_y = max(0.0, min(1.0, norm_y))
                norm_w = max(0.0, min(1.0, norm_w))
                norm_h = max(0.0, min(1.0, norm_h))

                regions.append(
                    LayoutRegion(
                        name=region_name,
                        x=round(norm_x, 6),
                        y=round(norm_y, 6),
                        width=round(norm_w, 6),
                        height=round(norm_h, 6),
                    )
                )
                logger.debug(
                    f"OBS region '{region_name}': "
                    f"x={norm_x:.4f}, y={norm_y:.4f}, "
                    f"w={norm_w:.4f}, h={norm_h:.4f}"
                )
            except Exception as e:
                logger.warning(f"Failed to get transform for '{source_name}': {e}")
                continue

        layout = SceneLayout(
            regions=regions,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )
        logger.debug(
            f"OBS layout: {len(regions)} regions on "
            f"{canvas_width}x{canvas_height} canvas"
        )
        return layout

    def capture_screen(self, source_name: Optional[str] = None) -> Optional[str]:
        """
        Capture a screenshot from OBS (Phase 2 placeholder).

        Args:
            source_name: Optional source name to capture. If None, captures
                         the entire program output.

        Returns:
            Base64-encoded image string, or None if not available.
        """
        # Phase 2: Implement using GetSourceScreenshot
        logger.debug("OBS screen capture not yet implemented (Phase 2)")
        return None

    async def start_layout_polling(
        self,
        callback: Callable[["SceneLayout"], None],
        interval: float = 2.0,
    ) -> None:
        """
        Start periodic layout polling in the background.

        Args:
            callback: Async callback invoked with SceneLayout when layout changes.
            interval: Polling interval in seconds.
        """
        self.stop_layout_polling()
        self._polling_task = asyncio.create_task(self._poll_layout(callback, interval))
        logger.info(f"OBS layout polling started (interval: {interval}s)")

    def stop_layout_polling(self) -> None:
        """Stop layout polling if active."""
        if self._polling_task is not None and not self._polling_task.done():
            self._polling_task.cancel()
            logger.info("OBS layout polling stopped")
        self._polling_task = None

    async def _poll_layout(
        self,
        callback: Callable[["SceneLayout"], None],
        interval: float,
    ) -> None:
        """
        Background polling loop that detects layout changes.

        Args:
            callback: Async callback for layout changes.
            interval: Seconds between polls.
        """
        last_layout: Optional[SceneLayout] = None

        while True:
            try:
                layout = await asyncio.to_thread(self._get_layout_sync)
                if layout is not None and layout != last_layout:
                    await callback(layout)
                    last_layout = layout
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"OBS layout polling error: {e}")
                self._handle_connection_error(e)

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    def _handle_connection_error(self, error: Exception) -> None:
        """
        Handle connection errors, marking as disconnected if necessary.

        Args:
            error: The exception that occurred.
        """
        error_str = str(error).lower()
        connection_errors = [
            "connection",
            "closed",
            "refused",
            "reset",
            "broken pipe",
            "timeout",
        ]
        if any(keyword in error_str for keyword in connection_errors):
            logger.warning("OBS connection lost. Marking as disconnected.")
            self._connected = False
