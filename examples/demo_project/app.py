"""Tiny project used to demonstrate deterministic documentation drift."""

import argparse


def train(data_path: str, epochs: int = 50, batch_size: int = 32) -> dict[str, object]:
    """Return a training configuration for demonstration purposes."""

    return {
        "data_path": data_path,
        "epochs": epochs,
        "batch_size": batch_size,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Number of samples per batch",
    )
    parser.add_argument("--model-path", default="weights.pt", help="Model checkpoint path")
    return parser
