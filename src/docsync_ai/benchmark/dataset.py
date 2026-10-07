"""Frozen, reproducible controlled benchmark definitions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

BENCHMARK_VERSION = "benchmark-v1"

ISSUE_TYPES = {
    "DS001": "PARAMETER_NAME_MISMATCH",
    "DS002": "DEFAULT_VALUE_MISMATCH",
    "DS003": "CLI_OPTION_MISMATCH",
    "DS004": "CONFIG_KEY_MISMATCH",
    "DS005": "CALL_SIGNATURE_MISMATCH",
}


@dataclass(frozen=True, slots=True)
class DeterministicCase:
    case_id: str
    category: str
    expected_finding: bool
    expected_issue_type: str
    expected_doc_file: str
    expected_doc_line: int | None
    expected_code_entity: str
    mutation_type: str
    original_content: str
    modified_content: str
    notes: str
    files: dict[str, str]

    def ground_truth(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("files")
        return data


def _case(
    category: str,
    number: int,
    *,
    expected: bool,
    source: str,
    documentation: str,
    mutation_type: str,
    original: str,
    modified: str,
    entity: str,
    notes: str,
    extra_files: dict[str, str] | None = None,
    doc_line: int = 4,
) -> DeterministicCase:
    files = {"app.py": source, "README.md": documentation}
    files.update(extra_files or {})
    return DeterministicCase(
        case_id=f"{category.lower()}-{number:02d}",
        category=category,
        expected_finding=expected,
        expected_issue_type=ISSUE_TYPES[category],
        expected_doc_file="README.md",
        expected_doc_line=doc_line if expected else None,
        expected_code_entity=entity,
        mutation_type=mutation_type,
        original_content=original,
        modified_content=modified,
        notes=notes,
        files=files,
    )


def deterministic_cases() -> list[DeterministicCase]:
    cases: list[DeterministicCase] = []
    cases.extend(_ds001_cases())
    cases.extend(_ds002_cases())
    cases.extend(_ds003_cases())
    cases.extend(_ds004_cases())
    cases.extend(_ds005_cases())
    return cases


def _ds001_cases() -> list[DeterministicCase]:
    source = "def train(data_path='data.csv', epochs=50, batch_size=32):\n    pass\n"
    positives = [
        ("path", "data_path", "abbreviated keyword"),
        ("dataset", "data_path", "generic dataset keyword"),
        ("file_path", "data_path", "similar but nonexistent keyword"),
        ("epoch_count", "epochs", "renamed count keyword"),
        ("batch", "batch_size", "shortened batch keyword"),
        ("input_file", "data_path", "legacy input keyword"),
    ]
    cases = []
    for index, (wrong, correct, note) in enumerate(positives, 1):
        original = f'train({correct}="data.csv")'
        modified = f'train({wrong}="data.csv")'
        docs = f"# Training\n\n```python\n{modified}\n```\n"
        cases.append(
            _case(
                "DS001",
                index,
                expected=True,
                source=source,
                documentation=docs,
                mutation_type="rename_keyword_argument",
                original=original,
                modified=modified,
                entity="train",
                notes=note,
            )
        )
    negatives = [
        ('dataset = "x.csv"\ntrain(dataset)', "caller-local variable is positional"),
        ('train("x.csv")', "literal positional argument"),
        ('train(data_path="x.csv")', "valid keyword argument"),
        ('train("x.csv", epochs=100)', "valid explicit optional value"),
        ("value = get_path()\ntrain(value)", "call expression assigned locally"),
        ('train(data_path="x.csv", batch_size=64)', "multiple valid keywords"),
    ]
    for offset, (snippet, note) in enumerate(negatives, 7):
        docs = f"# Training\n\n```python\n{snippet}\n```\n"
        cases.append(
            _case(
                "DS001",
                offset,
                expected=False,
                source=source,
                documentation=docs,
                mutation_type="negative_edge_case",
                original=snippet,
                modified=snippet,
                entity="train",
                notes=note,
            )
        )
    return cases


def _ds002_cases() -> list[DeterministicCase]:
    positives = [
        ("epochs=50", "epochs default = 50", "epochs default = 100", "configure"),
        ('mode="fast"', 'mode default = "fast"', 'mode default = "safe"', "configure"),
        ("enabled=True", "enabled default = true", "enabled default = false", "configure"),
        ("cache=None", "cache default = None", 'cache default = "memory"', "configure"),
        ("ratio=0.5", "ratio default = 0.5", "ratio default = 0.75", "configure"),
        ("layers=[32, 64]", "layers default = [32, 64]", "layers default = [64, 128]", "configure"),
    ]
    cases = []
    for index, (signature, original, modified, entity) in enumerate(positives, 1):
        source = f"def configure({signature}):\n    pass\n"
        docs = f"# Configuration\n\n{modified}\n"
        cases.append(
            _case(
                "DS002",
                index,
                expected=True,
                source=source,
                documentation=docs,
                mutation_type="change_documented_default",
                original=original,
                modified=modified,
                entity=entity,
                notes="explicit documented default differs from static code default",
            )
        )
    negatives = [
        ("epochs=50", "epochs default = 50", "matching integer default"),
        ("enabled=True", "enabled default = true", "normalized boolean default"),
        ("cache=None", "cache default = None", "matching None default"),
        ('mode="fast"', 'mode default = "fast"', "matching string default"),
        ("layers=[32, 64]", "layers default = [32, 64]", "matching list default"),
        (
            "epochs=50",
            "```python\nconfigure(epochs=100)\n```",
            "example value is not a default claim",
        ),
    ]
    for offset, (signature, statement, note) in enumerate(negatives, 7):
        source = f"def configure({signature}):\n    pass\n"
        docs = f"# Configuration\n\n{statement}\n"
        cases.append(
            _case(
                "DS002",
                offset,
                expected=False,
                source=source,
                documentation=docs,
                mutation_type="negative_edge_case",
                original=statement,
                modified=statement,
                entity="configure",
                notes=note,
            )
        )
    return cases


def _argparse_source(option: str) -> str:
    return (
        f'import argparse\n\nparser = argparse.ArgumentParser()\nparser.add_argument("{option}")\n'
    )


def _ds003_cases() -> list[DeterministicCase]:
    positives = [
        ("--model-path", "--model"),
        ("--batch-size", "--batch"),
        ("--output-dir", "--output"),
        ("--learning-rate", "--lr-rate"),
        ("--checkpoint-file", "--checkpoint"),
        ("--max-retries", "--retry-count"),
    ]
    cases = []
    for index, (actual, documented) in enumerate(positives, 1):
        command = f"python app.py {documented} value"
        docs = f"# CLI\n\n```bash\n{command}\n```\n"
        cases.append(
            _case(
                "DS003",
                index,
                expected=True,
                source=_argparse_source(actual),
                documentation=docs,
                mutation_type="rename_cli_option",
                original=f"python app.py {actual} value",
                modified=command,
                entity=actual,
                notes="explicit fenced CLI command uses a removed option",
            )
        )
    negatives = [
        ("--model-path", "```bash\npython app.py --model-path weights.pt\n```", "valid CLI option"),
        ("--batch-size", "The prose token --example is not a command.", "option-like prose"),
        ("--output-dir", "`--example` is illustrative inline code.", "inline code is not CLI"),
        ("--learning-rate", "```python\ntext = '--old-option'\n```", "Python fence is not CLI"),
        ("--checkpoint-file", "```bash\npython app.py\n```", "CLI command with no options"),
        ("--max-retries", "Use the retry option described below.", "natural-language description"),
    ]
    for offset, (actual, content, note) in enumerate(negatives, 7):
        docs = f"# CLI\n\n{content}\n"
        cases.append(
            _case(
                "DS003",
                offset,
                expected=False,
                source=_argparse_source(actual),
                documentation=docs,
                mutation_type="negative_edge_case",
                original=content,
                modified=content,
                entity=actual,
                notes=note,
            )
        )
    return cases


def _yaml(parent: str, key: str, value: str = "32") -> str:
    return f"{parent}:\n  {key}: {value}\n"


def _ds004_cases() -> list[DeterministicCase]:
    positives = [
        ("training", "batch_size", "batch"),
        ("training", "epochs", "epoch"),
        ("model", "checkpoint_path", "checkpoint"),
        ("logging", "output_dir", "output"),
        ("optimizer", "learning_rate", "lr"),
        ("data", "cache_enabled", "cache"),
    ]
    cases = []
    for index, (parent, actual, documented) in enumerate(positives, 1):
        source_config = _yaml(parent, actual)
        documented_config = _yaml(parent, documented)
        docs = f"# Config\n\n```yaml\n{documented_config}```\n"
        cases.append(
            _case(
                "DS004",
                index,
                expected=True,
                source="def load_config():\n    pass\n",
                documentation=docs,
                mutation_type="rename_config_key",
                original=source_config,
                modified=documented_config,
                entity=f"{parent}.{actual}",
                notes="explicit fenced configuration uses a stale nested key",
                extra_files={"config.yaml": source_config},
                doc_line=5,
            )
        )
    negatives = [
        ("training", "batch_size", "```yaml\ntraining:\n  batch_size: 32\n```", "matching key"),
        (
            "training",
            "batch-size",
            "```yaml\ntraining:\n  batch_size: 32\n```",
            "hyphen/underscore normalization",
        ),
        (
            "model",
            "checkpoint_path",
            "The checkpoint field is described in prose.",
            "natural language",
        ),
        ("logging", "output_dir", "`logging.output` is an example name.", "inline code only"),
        ("optimizer", "learning_rate", "```python\nconfig = {'lr': 0.1}\n```", "Python fence"),
        ("data", "cache_enabled", "No configuration snippet is required here.", "no explicit key"),
    ]
    for offset, (parent, actual, content, note) in enumerate(negatives, 7):
        source_config = _yaml(parent, actual)
        docs = f"# Config\n\n{content}\n"
        cases.append(
            _case(
                "DS004",
                offset,
                expected=False,
                source="def load_config():\n    pass\n",
                documentation=docs,
                mutation_type="negative_edge_case",
                original=content,
                modified=content,
                entity=f"{parent}.{actual}",
                notes=note,
                extra_files={"config.yaml": source_config},
            )
        )
    return cases


def _python_doc(snippet: str) -> str:
    return f"# API\n\n```python\n{snippet}\n```\n"


def _ds005_cases() -> list[DeterministicCase]:
    positives = [
        (
            "def train(data_path, epochs=50):\n    pass\n",
            "train()",
            'train("data.csv")',
            "missing required argument",
        ),
        (
            "def train(data_path, epochs=50):\n    pass\n",
            'train("x", 50, 32)',
            'train("x", 50)',
            "too many positional arguments",
        ),
        (
            "def train(data_path, epochs=50):\n    pass\n",
            'train("x", data_path="y")',
            'train("x")',
            "multiple values for one parameter",
        ),
        (
            "def train(data_path, labels, epochs=50):\n    pass\n",
            'train("x")',
            'train("x", "labels.csv")',
            "second required argument missing",
        ),
        (
            "def train(data_path, *, mode):\n    pass\n",
            'train("x")',
            'train("x", mode="fast")',
            "required keyword-only argument missing",
        ),
        (
            "async def train(data_path, checkpoint):\n    pass\n",
            'train("x")',
            'train("x", "model.pt")',
            "async function signature drift",
        ),
    ]
    cases = []
    for index, (source, modified, original, note) in enumerate(positives, 1):
        cases.append(
            _case(
                "DS005",
                index,
                expected=True,
                source=source,
                documentation=_python_doc(modified),
                mutation_type="change_call_signature",
                original=original,
                modified=modified,
                entity="train",
                notes=note,
            )
        )
    negatives = [
        (
            "def train(data_path, epochs=50):\n    pass\n",
            'train("x")',
            "required provided, optional omitted",
        ),
        (
            "def train(data_path, epochs=50):\n    pass\n",
            'train("x", epochs=100)',
            "valid explicit optional argument",
        ),
        ("def train(*paths):\n    pass\n", 'train("a", "b", "c")', "valid varargs"),
        (
            "def train(data_path, **options):\n    pass\n",
            'train("x", custom=True)',
            "valid arbitrary keyword",
        ),
        (
            "def train(data_path, epochs=50):\n    pass\n",
            "train(*args, **kwargs)",
            "unpacking is conservatively skipped",
        ),
        (
            "def train(data_path, *, mode='fast'):\n    pass\n",
            'train("x")',
            "optional keyword-only omitted",
        ),
    ]
    for offset, (source, snippet, note) in enumerate(negatives, 7):
        cases.append(
            _case(
                "DS005",
                offset,
                expected=False,
                source=source,
                documentation=_python_doc(snippet),
                mutation_type="negative_edge_case",
                original=snippet,
                modified=snippet,
                entity="train",
                notes=note,
            )
        )
    return cases


def semantic_cases() -> list[dict[str, Any]]:
    rows = [
        (
            "data_path",
            "path",
            "CONSISTENT",
            "Both descriptions identify the training dataset path.",
        ),
        (
            "output_directory",
            "save_dir",
            "CONSISTENT",
            "Both identify where generated files are saved.",
        ),
        (
            "max_retry_count",
            "retry_limit",
            "CONSISTENT",
            "Both limit retry attempts in the same operation.",
        ),
        (
            "learning_rate",
            "lr",
            "CONSISTENT",
            "The documentation explicitly defines lr as learning rate.",
        ),
        (
            "checkpoint_path",
            "model_file",
            "CONSISTENT",
            "Context says the file is a model checkpoint.",
        ),
        (
            "batch_size",
            "samples_per_batch",
            "CONSISTENT",
            "Both specify examples processed in one batch.",
        ),
        (
            "timeout_seconds",
            "request_timeout",
            "CONSISTENT",
            "Both refer to the request timeout in seconds.",
        ),
        (
            "source_language",
            "input_lang",
            "CONSISTENT",
            "Both identify the language of input text.",
        ),
        (
            "destination",
            "output_path",
            "CONSISTENT",
            "Both identify the produced artifact location.",
        ),
        ("validation_data", "dev_set", "CONSISTENT", "Context defines dev set as validation data."),
        (
            "data_path",
            "output_path",
            "INCONSISTENT",
            "Input dataset and output location are different concepts.",
        ),
        (
            "epochs",
            "batch_size",
            "INCONSISTENT",
            "Training iterations and batch size are distinct.",
        ),
        (
            "model_name",
            "dataset_name",
            "INCONSISTENT",
            "Model identity and dataset identity are distinct.",
        ),
        (
            "cache_enabled",
            "cache_directory",
            "INCONSISTENT",
            "A boolean switch is not a directory path.",
        ),
        (
            "timeout_seconds",
            "max_retries",
            "INCONSISTENT",
            "Time limit and retry count are distinct controls.",
        ),
        (
            "input_format",
            "output_format",
            "INCONSISTENT",
            "Input and output formats have different roles.",
        ),
        (
            "checkpoint_path",
            "log_path",
            "INCONSISTENT",
            "Model checkpoint and log destination differ.",
        ),
        ("seed", "worker_count", "INCONSISTENT", "Random seed and concurrency are unrelated."),
        ("device", "precision", "INCONSISTENT", "Compute device and numeric precision differ."),
        ("token", "token_limit", "INCONSISTENT", "Credential token and token-count limit differ."),
        (
            "path",
            "location",
            "UNCERTAIN",
            "Context does not state what resource either path identifies.",
        ),
        ("mode", "strategy", "UNCERTAIN", "The allowed values and behavioral scope are omitted."),
        ("size", "limit", "UNCERTAIN", "Units and constrained object are unspecified."),
        (
            "source",
            "input",
            "UNCERTAIN",
            "The terms may coincide, but the surrounding interface is ambiguous.",
        ),
    ]
    cases = []
    for index, (code_parameter, doc_parameter, decision, reason) in enumerate(rows, 1):
        cases.append(
            {
                "case_id": f"semantic-{index:02d}",
                "category": "DS001_SEMANTIC",
                "function_context": "def process(...): statically analyzed interface parameter",
                "code_parameter": code_parameter,
                "documentation_parameter": doc_parameter,
                "short_code_context": f"process parameter `{code_parameter}`",
                "short_documentation_context": (
                    f"Parameters: `{doc_parameter}` in the same process operation"
                ),
                "human_ground_truth": decision,
                "human_reason": reason,
            }
        )
    return cases
