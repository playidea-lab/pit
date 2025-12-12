"""pit chat CLI command"""

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

app = typer.Typer(help="Chat with pit AI assistant")
console = Console()


@app.command("start")
def start():
    """Start interactive chat session"""
    try:
        from pit.core.chat import PitChat
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[yellow]Create .env file with ANTHROPIC_API_KEY[/yellow]")
        raise typer.Exit(1)

    console.print(Panel(
        "[bold]pit chat[/bold] - AI 어시스턴트와 대화하세요\n"
        "종료: quit, exit, q\n"
        "예시: '현재 프로젝트 상태 알려줘', '새 Feature 만들어줘'",
        title="pit AI Assistant",
    ))

    chat = PitChat()

    while True:
        try:
            user_input = console.input("\n[bold cyan]You>[/bold cyan] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]세션 종료[/yellow]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            console.print("[yellow]세션 종료[/yellow]")
            break

        try:
            with console.status("[bold green]생각 중..."):
                response = chat.chat(user_input)

            console.print()
            console.print(Panel(Markdown(response), title="[bold green]pit[/bold green]", border_style="green"))

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


# Allow direct invocation: pit chat (without subcommand)
def chat_main():
    """Direct entry for pit chat"""
    start()
