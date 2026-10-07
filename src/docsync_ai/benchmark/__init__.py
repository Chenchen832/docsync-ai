"""Controlled benchmark generation and evaluation."""

from .dataset import BENCHMARK_VERSION, deterministic_cases, semantic_cases
from .evaluator import classification_metrics, evaluate_benchmark

__all__ = [
    "BENCHMARK_VERSION",
    "classification_metrics",
    "deterministic_cases",
    "evaluate_benchmark",
    "semantic_cases",
]
