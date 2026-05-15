import logging
import winreg

_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "WorkloadAnalyzer"
_log = logging.getLogger(__name__)


def enable(exe_path: str) -> None:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
    except OSError as e:
        _log.warning("Autostart enable failed: %s", e)


def disable() -> None:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, _APP_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass
    except OSError as e:
        _log.warning("Autostart disable failed: %s", e)


def is_enabled() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY)
        winreg.QueryValueEx(key, _APP_NAME)
        winreg.CloseKey(key)
        return True
    except (FileNotFoundError, OSError):
        return False
