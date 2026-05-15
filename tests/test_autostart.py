from unittest.mock import MagicMock, patch


def test_enable_writes_registry_entry():
    mock_key = MagicMock()
    with patch("workload_analyzer.services.autostart.winreg.OpenKey", return_value=mock_key), \
         patch("workload_analyzer.services.autostart.winreg.SetValueEx") as mock_set, \
         patch("workload_analyzer.services.autostart.winreg.CloseKey"):
        from workload_analyzer.services.autostart import enable
        enable("C:\\WorkloadAnalyzer.exe")
    args = mock_set.call_args[0]
    assert args[1] == "WorkloadAnalyzer"
    assert args[4] == "C:\\WorkloadAnalyzer.exe"


def test_disable_removes_registry_entry():
    mock_key = MagicMock()
    with patch("workload_analyzer.services.autostart.winreg.OpenKey", return_value=mock_key), \
         patch("workload_analyzer.services.autostart.winreg.DeleteValue") as mock_del, \
         patch("workload_analyzer.services.autostart.winreg.CloseKey"):
        from workload_analyzer.services.autostart import disable
        disable()
    mock_del.assert_called_once_with(mock_key, "WorkloadAnalyzer")


def test_disable_is_silent_when_not_enabled():
    with patch("workload_analyzer.services.autostart.winreg.OpenKey", return_value=MagicMock()), \
         patch("workload_analyzer.services.autostart.winreg.DeleteValue", side_effect=FileNotFoundError), \
         patch("workload_analyzer.services.autostart.winreg.CloseKey"):
        from workload_analyzer.services.autostart import disable
        disable()  # must not raise


def test_is_enabled_returns_true_when_entry_exists():
    with patch("workload_analyzer.services.autostart.winreg.OpenKey", return_value=MagicMock()), \
         patch("workload_analyzer.services.autostart.winreg.QueryValueEx", return_value=("C:\\exe", 1)), \
         patch("workload_analyzer.services.autostart.winreg.CloseKey"):
        from workload_analyzer.services.autostart import is_enabled
        assert is_enabled() is True


def test_is_enabled_returns_false_when_entry_missing():
    with patch("workload_analyzer.services.autostart.winreg.OpenKey", return_value=MagicMock()), \
         patch("workload_analyzer.services.autostart.winreg.QueryValueEx", side_effect=FileNotFoundError), \
         patch("workload_analyzer.services.autostart.winreg.CloseKey"):
        from workload_analyzer.services.autostart import is_enabled
        assert is_enabled() is False
