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


@cli.command()
@click.argument('document', type=click.Path(exists=True))
@click.option('--profile', '-p', help='Document profile JSON (optional)')
@click.option('--strategy', '-s', type=click.Choice(['auto', 'fast', 'layout', 'vision']), default='auto')
@click.option('--output', '-o', default='.refinery/extractions', help='Output directory')
def extract(document, profile, strategy, output):
    """Extract content from document using optimal strategy"""
    
    from .agents.triage import TriageAgent
    from .agents.extractor import ExtractionRouter
    from .models.document import DocumentProfile
    
    console.print(f"[bold blue]⚙️ Extracting:[/bold blue] {document}")
    
    with Progress() as progress:
        task = progress.add_task("Extracting...", total=3)
        
        # Step 1: Get or create profile
        if profile:
            with open(profile, 'r') as f:
                import json
                profile_data = json.load(f)
                doc_profile = DocumentProfile(**profile_data)
        else:
            agent = TriageAgent()
            doc_profile = agent.analyze(document)
            progress.update(task, advance=1, description="Triage complete")
        
        # Step 2: Route to extractor
        router = ExtractionRouter()
        if strategy != 'auto':
            # Override strategy
            from .models.enums import StrategyType
            doc_profile.recommended_strategy = StrategyType(strategy)
        
        result = router.extract(Path(document), doc_profile)
        progress.update(task, advance=1, description="Extraction complete")
        
        # Step 3: Save result
        output_dir = Path(output)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{doc_profile.doc_id}.json"
        output_path.write_text(result.to_json())
        progress.update(task, advance=1, description="Saving complete")
    
    console.print(f"[green]✅ Extraction saved to:[/green] {output_path}")
    
    # Show summary
    table = Table(title="Extraction Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    
    table.add_row("Strategy", result.extraction_strategy.value)
    table.add_row("Confidence", f"{result.confidence_score:.1%}")
    table.add_row("Cost", f"${result.cost_usd:.4f}")
    table.add_row("Time", f"{result.processing_time_sec:.2f}s")
    table.add_row("Text Blocks", str(len(result.text_blocks)))
    table.add_row("Tables", str(len(result.tables)))
    table.add_row("Figures", str(len(result.figures)))
    
    console.print(table)


@cli.command()
def ledger():
    """Show extraction ledger summary"""
    from .agents.extractor import ExtractionRouter
    
    router = ExtractionRouter()
    summary = router.get_ledger_summary()
    
    console.print("[bold]📊 Extraction Ledger Summary[/bold]")
    console.print(f"Total Extractions: {summary['total_extractions']}")
    console.print(f"Total Cost: ${summary['total_cost']:.4f}")
    console.print(f"Average Confidence: {summary['avg_confidence']:.1%}")
    
    if summary.get('by_strategy'):
        console.print("\nBy Strategy:")
        for strategy, count in summary['by_strategy'].items():
            console.print(f"  {strategy}: {count}")

if __name__ == "__main__":
    cli()