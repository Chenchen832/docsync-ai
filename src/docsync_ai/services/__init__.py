"""Application services shared by CLI and Web entry points."""

from .analysis_service import analyze_project

__all__ = ["analyze_project"]
