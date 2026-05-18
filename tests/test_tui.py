from ui.tui import OPCConsole


def test_console_exposes_main_status_methods():
    console = OPCConsole()

    assert callable(console.print_section)
    assert callable(console.print_info)
