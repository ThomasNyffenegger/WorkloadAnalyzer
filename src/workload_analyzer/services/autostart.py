import logging
import winreg

_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "WorkloadAnalyzer"
_log = logging.getLogger(__name__)


def enable(exe_path: str) -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            # Quoted like every other Run entry on the system (OneDrive,
            # Teams, ...) — unquoted paths break if the exe's directory ever
            # contains a space (e.g. a username with a space, or a
            # non-default Program Files install).
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
    except OSError as e:
        _log.warning("Autostart enable failed: %s", e)


def disable() -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _APP_NAME)
    except FileNotFoundError:
        pass
    except OSError as e:
        _log.warning("Autostart disable failed: %s", e)


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY) as key:
            winreg.QueryValueEx(key, _APP_NAME)
        return True
    except (FileNotFoundError, OSError):
        return False
