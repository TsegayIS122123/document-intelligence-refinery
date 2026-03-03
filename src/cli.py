"""Command-line interface for the Document Intelligence Refinery."""

import click
from pathlib import Path
import json
from rich.console import Console
from rich.table import Table
from rich.progress import Progress

console = Console()

@click.group()
def cli():
    """Document Intelligence Refinery - Transform documents into queryable knowledge."""
    pass

@cli.command()
@click.argument('document', type=click.Path(exists=True))
@click.option('--output', '-o', help='Output directory for profile')
def triage(document, output):
    """Run triage on a document to generate profile."""
    console.print(f"[bold green]🔍 Triaging:[/bold green] {document}")
    # TODO: Implement triage
    console.print("[yellow]Triage not yet implemented[/yellow]")

@cli.command()
@click.argument('document', type=click.Path(exists=True))
@click.option('--strategy', '-s', type=click.Choice(['auto', 'fast', 'layout', 'vision']), default='auto')
@click.option('--output', '-o', help='Output directory for extraction')
def extract(document, strategy, output):
    """Extract content from document using optimal strategy."""
    console.print(f"[bold blue]⚙️ Extracting:[/bold blue] {document} with strategy {strategy}")
    # TODO: Implement extraction
    console.print("[yellow]Extraction not yet implemented[/yellow]")

@cli.command()
@click.argument('document', type=click.Path(exists=True))
def index(document):
    """Build PageIndex and chunks for document."""
    console.print(f"[bold magenta]🗺️ Building index:[/bold magenta] {document}")
    # TODO: Implement indexing
    console.print("[yellow]Indexing not yet implemented[/yellow]")

@cli.command()
@click.argument('query')
@click.argument('document', type=click.Path(exists=True))
@click.option('--audit/--no-audit', default=False, help='Run in audit mode')
def query(query, document, audit):
    """Query a document with provenance tracking."""
    mode = "🔍 Audit Mode" if audit else "💬 Query Mode"
    console.print(f"[bold cyan]{mode}:[/bold cyan] {query}")
    # TODO: Implement query
    console.print("[yellow]Query not yet implemented[/yellow]")

@cli.command()
@click.argument('document', type=click.Path(exists=True))
def demo(document):
    """Run complete demo pipeline on a document."""
    console.print("[bold]🎥 Running Demo Pipeline[/bold]")
    console.print("=" * 50)
    
    # Step 1: Triage
    console.print("\n[bold green]Step 1: Triage[/bold green]")
    # TODO: Run triage
    
    # Step 2: Extraction
    console.print("\n[bold blue]Step 2: Extraction[/bold blue]")
    # TODO: Run extraction
    
    # Step 3: PageIndex
    console.print("\n[bold magenta]Step 3: PageIndex[/bold magenta]")
    # TODO: Build index
    
    # Step 4: Query
    console.print("\n[bold cyan]Step 4: Query[/bold cyan]")
    # TODO: Run sample queries
    
    console.print("\n[bold green]✅ Demo Complete[/bold green]")

if __name__ == "__main__":
    cli()