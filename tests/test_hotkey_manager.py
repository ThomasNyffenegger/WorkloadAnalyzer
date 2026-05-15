from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(autouse=True)
def mock_ctypes(monkeypatch):
    """Prevent real RegisterHotKey calls during tests."""
    mock_user32 = MagicMock()
    mock_user32.RegisterHotKey.return_value = 1   # success
    mock_user32.UnregisterHotKey.return_value = 1
    with patch("workload_analyzer.services.hotkey_manager.ctypes") as mock_ctypes:
        mock_ctypes.windll.user32 = mock_user32
        yield mock_ctypes


def test_register_calls_RegisterHotKey(qtbot, mock_ctypes):
    from workload_analyzer.services.hotkey_manager import GlobalHotkeyManager
    manager = GlobalHotkeyManager()
    qtbot.addWidget(manager._sink)

    manager.register(1)

    mock_ctypes.windll.user32.RegisterHotKey.assert_called_once()
    args = mock_ctypes.windll.user32.RegisterHotKey.call_args[0]
    assert args[1] == 1           # hotkey id = n
    assert args[2] == 0x0006      # MOD_CONTROL | MOD_SHIFT
    assert args[3] == 0x31        # VK_1


def test_register_all_nine_hotkeys(qtbot, mock_ctypes):
    from workload_analyzer.services.hotkey_manager import GlobalHotkeyManager
    manager = GlobalHotkeyManager()
    qtbot.addWidget(manager._sink)

    for i in range(1, 10):
        manager.register(i)

    assert mock_ctypes.windll.user32.RegisterHotKey.call_count == 9


def test_register_ignores_out_of_range(qtbot, mock_ctypes):
    from workload_analyzer.services.hotkey_manager import GlobalHotkeyManager
    manager = GlobalHotkeyManager()
    qtbot.addWidget(manager._sink)

    manager.register(0)
    manager.register(10)

    mock_ctypes.windll.user32.RegisterHotKey.assert_not_called()


def test_unregister_all_calls_UnregisterHotKey(qtbot, mock_ctypes):
    from workload_analyzer.services.hotkey_manager import GlobalHotkeyManager
    manager = GlobalHotkeyManager()
    qtbot.addWidget(manager._sink)
    manager.register(1)
    manager.register(2)

    manager.unregister_all()

    assert mock_ctypes.windll.user32.UnregisterHotKey.call_count == 2


def test_triggered_signal_emits_n(qtbot, mock_ctypes):
    from workload_analyzer.services.hotkey_manager import GlobalHotkeyManager
    manager = GlobalHotkeyManager()
    qtbot.addWidget(manager._sink)
    manager.register(3)

    received = []
    manager.triggered.connect(received.append)

    # Simulate WM_HOTKEY by calling internal handler directly
    manager._on_hotkey(3)

    assert received == [3]
