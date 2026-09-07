from unittest.mock import MagicMock, patch


def _mock_com_folder():
    """Build a (scheduler, folder) mock pair matching the shape autostart.py expects."""
    scheduler = MagicMock()
    folder = MagicMock()
    task_def = MagicMock()
    scheduler.NewTask.return_value = task_def
    return scheduler, folder, task_def


def test_enable_registers_logon_task():
    scheduler, folder, task_def = _mock_com_folder()
    with patch("workload_analyzer.services.autostart._com_folder", return_value=(scheduler, folder)):
        from workload_analyzer.services.autostart import enable
        enable("C:\\WorkloadAnalyzer.exe")

    task_def.Triggers.Create.assert_called_once_with(9)  # TASK_TRIGGER_LOGON
    task_def.Actions.Create.assert_called_once_with(0)    # TASK_ACTION_EXEC
    action = task_def.Actions.Create.return_value
    assert action.Path == "C:\\WorkloadAnalyzer.exe"

    args, kwargs = folder.RegisterTaskDefinition.call_args
    assert args[0] == "WorkloadAnalyzer"
    assert args[1] is task_def


def test_disable_deletes_task():
    scheduler, folder, _ = _mock_com_folder()
    with patch("workload_analyzer.services.autostart._com_folder", return_value=(scheduler, folder)):
        from workload_analyzer.services.autostart import disable
        disable()

    folder.DeleteTask.assert_called_once_with("WorkloadAnalyzer", 0)


def test_disable_is_silent_when_not_enabled():
    scheduler, folder, _ = _mock_com_folder()
    folder.DeleteTask.side_effect = Exception("(-2147024894, ... 80070002 ...)")
    with patch("workload_analyzer.services.autostart._com_folder", return_value=(scheduler, folder)):
        from workload_analyzer.services.autostart import disable
        disable()  # must not raise


def test_is_enabled_returns_true_when_task_exists():
    scheduler, folder, _ = _mock_com_folder()
    folder.GetTask.return_value = MagicMock()
    with patch("workload_analyzer.services.autostart._com_folder", return_value=(scheduler, folder)):
        from workload_analyzer.services.autostart import is_enabled
        assert is_enabled() is True


def test_is_enabled_returns_false_when_task_missing():
    scheduler, folder, _ = _mock_com_folder()
    folder.GetTask.side_effect = Exception("not found")
    with patch("workload_analyzer.services.autostart._com_folder", return_value=(scheduler, folder)):
        from workload_analyzer.services.autostart import is_enabled
        assert is_enabled() is False
