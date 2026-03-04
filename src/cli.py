"""Command-line interface for the Document Intelligence Refinery."""

import click
from pathlib import Path
import json
from rich.console import Console
from rich.table import Table
from rich.progress import Progress

from .agents.triage import TriageAgent
from .models.document import DocumentProfileSummary


console = Console()

@click.group()
def cli():
    """Document Intelligence Refinery"""
    pass

@cli.command()
@click.argument('document', type=click.Path(exists=True))
@click.option('--output', '-o', default='.refinery/profiles', help='Output directory')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed analysis')
def triage(document, output, verbose):
    """Run triage on a document to generate profile"""
    
    console.print(f"[bold blue]🔍 Running Triage on:[/bold blue] {document}")
    
    with Progress() as progress:
        task = progress.add_task("Analyzing document...", total=1)
        
        agent = TriageAgent()
        profile = agent.analyze(document)
        
        # Save profile
        output_path = agent.save_profile(profile, output)
        
        progress.update(task, advance=1)
    
    console.print(f"[green]✅ Profile saved to:[/green] {output_path}")
    
    if verbose:
        agent.print_summary(profile)
    else:
        # Show summary table
        summary = DocumentProfileSummary.from_profile(profile)
        
        table = Table(title="Document Profile Summary")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        
        table.add_row("Document", summary.filename)
        table.add_row("Origin Type", summary.origin_type.value)
        table.add_row("Layout", summary.layout_complexity.value)
        table.add_row("Domain", summary.domain_hint.value)
        table.add_row("Strategy", summary.recommended_strategy.value)
        table.add_row("Confidence", summary.profile_confidence.value)
        table.add_row("Est. Cost", f"${summary.estimated_cost_usd:.4f}")
        
        console.print(table)
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