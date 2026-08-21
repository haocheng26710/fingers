"""Plan-bound synthetic measurement-matrix and research analysis."""

from .research import (
    PublishedResearchAnalysis,
    ResearchDataset,
    load_research_dataset,
    run_research_analysis,
)

__all__ = [
    "PublishedResearchAnalysis",
    "ResearchDataset",
    "load_research_dataset",
    "run_research_analysis",
]
