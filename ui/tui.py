"""OPC TUI — Rich-based terminal UI for the optimizer."""

import logging
from typing import Any, Dict, Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.syntax import Syntax
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

logger = logging.getLogger("opc.tui")


class OPCConsole:
    """Rich TUI console wrapper with graceful fallback to plain print."""
    
    def __init__(self):
        if HAS_RICH:
            self.console = Console()
            self._rich = True
        else:
            self.console = None
            self._rich = False
            logger.debug("rich not installed, using plain output")
    
    def print_header(self):
        """Print startup banner."""
        if self._rich:
            banner = Text()
            banner.append("🤖 OPC Local Code Optimizer", style="bold cyan")
            banner.append(" — v1.0.0", style="dim")
            self.console.print(Panel(banner, border_style="bright_blue", box=box.DOUBLE))
        else:
            print("=" * 60)
            print("🤖 OPC Local Code Optimizer — v1.0.0")
            print("=" * 60)
    
    def print_config(self, config: Dict[str, Any]):
        """Print configuration summary."""
        if self._rich:
            table = Table(title="⚙️ Configuration", box=box.SIMPLE, show_header=False)
            table.add_column("Key", style="bold")
            table.add_column("Value", style="green")
            for key, val in config.items():
                table.add_row(str(key), str(val))
            self.console.print(table)
        else:
            for key, val in config.items():
                print(f"  {key}: {val}")
    
    def print_round_start(self, round_num: int, max_rounds: int, goal: str):
        """Print round start heading."""
        if self._rich:
            header = f"🔄 Round {round_num}/{max_rounds}"
            self.console.print()
            self.console.rule(header, style="bright_yellow")
            self.console.print(f"  🎯 {goal}", style="dim")
        else:
            print(f"\n{'='*40}")
            print(f"🔄 Round {round_num}/{max_rounds} | 🎯 {goal}")
            print(f"{'='*40}")
    
    def print_phase(self, phase_name: str, emoji: str = "▶"):
        """Print current phase indicator."""
        if self._rich:
            self.console.print(f"\n{emoji} [bold magenta]{phase_name}[/bold magenta]")
        else:
            print(f"\n{emoji} {phase_name}")
    
    def print_diff_summary(self, diff_text: str):
        """Print code diff with syntax highlighting."""
        if not diff_text or diff_text == "No file changes proposed.":
            if self._rich:
                self.console.print("  [dim]No changes made[/dim]")
            else:
                print("  No changes made")
            return
        
        if self._rich:
            # Show truncated if too long
            display = diff_text[:2000] + "..." if len(diff_text) > 2000 else diff_text
            syntax = Syntax(display, "diff", theme="monokai", line_numbers=False)
            self.console.print(Panel(syntax, title="📝 Changes", border_style="green", expand=False))
        else:
            lines = diff_text.split("\n")[:20]
            for line in lines:
                print(f"  {line}")
            if len(diff_text.split("\n")) > 20:
                print("  ... (truncated)")
    
    def print_token_usage(self, prompt: int, completion: int, total: int, calls: int):
        """Print token usage dashboard."""
        if self._rich:
            table = Table(title="📊 Token Usage", box=box.ROUNDED)
            table.add_column("Metric", style="bold")
            table.add_column("Value", justify="right", style="cyan")
            table.add_row("API Calls", str(calls))
            table.add_row("Prompt Tokens", f"{prompt:,}")
            table.add_row("Completion Tokens", f"{completion:,}")
            table.add_row("Total Tokens", f"{total:,}")
            self.console.print(table)
        else:
            print(f"  API Calls: {calls} | Tokens: {prompt:,} + {completion:,} = {total:,}")
    
    def print_build_result(self, output: str, success: bool):
        """Print build result with status."""
        if self._rich:
            style = "green" if success else "red"
            icon = "✅" if success else "❌"
            title = f"{icon} Build {'Passed' if success else 'Failed'}"
            # Truncate long output
            display = output[:1500] + "..." if len(output) > 1500 else output
            self.console.print(Panel(display, title=title, border_style=style, expand=False))
        else:
            status = "PASSED" if success else "FAILED"
            print(f"  Build: {status}")
            for line in output.split("\n")[:10]:
                print(f"    {line}")
    
    def print_final_report(self, total_rounds: int, reports: list):
        """Print final completion report."""
        if self._rich:
            panel_content = f"Total rounds completed: {total_rounds}\n"
            panel_content += f"Reports generated: {len(reports)}"
            self.console.print()
            self.console.print(Panel(
                panel_content,
                title="🏁 Optimization Complete",
                border_style="bright_green",
                box=box.DOUBLE,
            ))
        else:
            print(f"\n🏁 Optimization Complete — {total_rounds} rounds, {len(reports)} reports")
    
    def print_error(self, message: str):
        """Print error message."""
        if self._rich:
            self.console.print(f"[bold red]❌ {message}[/bold red]")
        else:
            print(f"❌ {message}")
    
    def print_success(self, message: str):
        """Print success message."""
        if self._rich:
            self.console.print(f"[bold green]✅ {message}[/bold green]")
        else:
            print(f"✅ {message}")
