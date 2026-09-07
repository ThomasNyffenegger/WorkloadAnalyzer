"""Autostart via a Windows Scheduled Task ("At log on").

Two mechanisms were tried and rejected on a Komax-managed machine before
this one:

1. A plain HKCU\\...\\Run registry entry can be silently ignored at logon
   on locked-down/managed Windows machines: the entry survived reboots,
   pointed at a valid exe, and nothing (Defender, AppLocker, WDAC,
   Application/System event log) ever logged a block or a crash — yet the
   process never launched.
2. `schtasks.exe` (the command-line tool) is itself blocked on the same
   machine ("Zugriff verweigert" / access denied) regardless of which
   shell invokes it — likely a policy targeting this well-known
   living-off-the-land binary specifically.

The Task Scheduler COM API (`Schedule.Service`, the same API the
PowerShell `ScheduledTasks` module wraps) is not restricted and does
work reliably, so we talk to it directly via pywin32 instead of shelling
out.
"""
import logging
import os

_log = logging.getLogger(__name__)

_TASK_NAME = "WorkloadAnalyzer"

# Task Scheduler COM enum values (from the taskschd.h IDL — pywin32 doesn't
# expose named constants for these, so they're spelled out here).
_TASK_TRIGGER_LOGON = 9
_TASK_ACTION_EXEC = 0
_TASK_CREATE_OR_UPDATE = 6
_TASK_LOGON_INTERACTIVE_TOKEN = 3


def _current_user() -> str:
    return f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}"


def _com_folder():
    """Connect to the Task Scheduler and return its root folder.

    Must run inside a CoInitialize/CoUninitialize pair — callers own that.
    """
    import win32com.client
    scheduler = win32com.client.Dispatch("Schedule.Service")
    scheduler.Connect()
    return scheduler, scheduler.GetFolder("\\")


def _register_logon_task(exe_path: str) -> None:
    # Isolated in its own function so all COM object locals (scheduler,
    # folder, task_def, trigger, action) are released by refcounting when
    # this frame returns — releasing them *after* CoUninitialize() (which
    # happens if they're still alive in the caller's frame) makes pywin32
    # print a harmless but noisy "Win32 exception occurred releasing
    # IUnknown" warning.
    scheduler, folder = _com_folder()
    task_def = scheduler.NewTask(0)
    task_def.RegistrationInfo.Description = "Startet WorkloadAnalyzer beim Anmelden"
    task_def.Settings.Enabled = True
    task_def.Settings.StopIfGoingOnBatteries = False
    task_def.Settings.DisallowStartIfOnBatteries = False
    task_def.Settings.StartWhenAvailable = True

    trigger = task_def.Triggers.Create(_TASK_TRIGGER_LOGON)
    trigger.UserId = _current_user()

    action = task_def.Actions.Create(_TASK_ACTION_EXEC)
    action.Path = exe_path

    folder.RegisterTaskDefinition(
        _TASK_NAME, task_def, _TASK_CREATE_OR_UPDATE,
        "", "", _TASK_LOGON_INTERACTIVE_TOKEN,
    )


def _delete_logon_task() -> None:
    _, folder = _com_folder()
    try:
        folder.DeleteTask(_TASK_NAME, 0)
    except Exception as e:
        # 0x80070002 = ERROR_FILE_NOT_FOUND — task doesn't exist, not an error.
        if "80070002" not in str(e):
            _log.warning("Autostart disable failed: %s", e)


def _task_exists() -> bool:
    _, folder = _com_folder()
    try:
        folder.GetTask(_TASK_NAME)
        return True
    except Exception:
        return False


def enable(exe_path: str) -> None:
    try:
        import pythoncom
        pythoncom.CoInitialize()
        try:
            _register_logon_task(exe_path)
        finally:
            pythoncom.CoUninitialize()
    except Exception as e:
        _log.warning("Autostart enable failed: %s", e)


def disable() -> None:
    try:
        import pythoncom
        pythoncom.CoInitialize()
        try:
            _delete_logon_task()
        finally:
            pythoncom.CoUninitialize()
    except Exception as e:
        _log.warning("Autostart disable failed: %s", e)


def is_enabled() -> bool:
    try:
        import pythoncom
        pythoncom.CoInitialize()
        try:
            return _task_exists()
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        return False
