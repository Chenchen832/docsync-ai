from docsync_ai.models import FindingStatus
from docsync_ai.parsers import ConfigParser, MarkdownParser, PythonParser
from docsync_ai.rules import CallSignatureRule, CliOptionRule, ConfigKeyRule

ARGPARSE_CODE = """
import argparse

def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path")
    parser.add_argument("--batch-size", default=32)
    return parser
"""


def test_ds003_detects_unknown_option_in_fenced_cli_command():
    code = PythonParser().parse(ARGPARSE_CODE, file_path="train.py")
    docs = MarkdownParser().parse(
        "```bash\npython train.py --model weights.pt --batch-size 32\n```\n",
        file_path="README.md",
    )
    findings = CliOptionRule().check(code, docs)

    assert len(findings) == 1
    assert findings[0].rule_id == "DS003"
    assert findings[0].status == FindingStatus.CONFIRMED
    assert findings[0].doc_fact["documented_option"] == "--model"
    assert findings[0].code_fact["nearest_option"] == "--model-path"


def test_ds003_ignores_option_like_text_outside_cli_fence():
    code = PythonParser().parse(ARGPARSE_CODE, file_path="train.py")
    docs = MarkdownParser().parse("Use --model in prose.\n", file_path="README.md")

    assert CliOptionRule().check(code, docs) == []


def test_ds004_detects_explicit_missing_config_key():
    code = ConfigParser().parse(
        "training:\n  batch_size: 32\n",
        format_name="yaml",
        file_path="config.yaml",
    )
    docs = MarkdownParser().parse(
        "```yaml\ntraining:\n  batch: 32\n```\n",
        file_path="README.md",
    )
    findings = ConfigKeyRule().check(code, docs)

    assert len(findings) == 1
    assert findings[0].rule_id == "DS004"
    assert findings[0].status == FindingStatus.CONFIRMED
    assert findings[0].doc_fact["documented_key"] == "training.batch"
    assert findings[0].code_fact["nearest_key"] == "training.batch_size"


def test_ds004_ignores_matching_normalized_config_key():
    code = ConfigParser().parse(
        "training:\n  batch-size: 32\n",
        format_name="yaml",
        file_path="config.yaml",
    )
    docs = MarkdownParser().parse(
        "```yaml\ntraining:\n  batch_size: 32\n```\n",
        file_path="README.md",
    )

    assert ConfigKeyRule().check(code, docs) == []


def test_ds005_detects_missing_required_argument():
    code = PythonParser().parse(
        "def train(data_path, epochs=50):\n    pass\n",
        file_path="train.py",
    )
    docs = MarkdownParser().parse("```python\ntrain()\n```\n", file_path="README.md")
    findings = CallSignatureRule().check(code, docs)

    assert len(findings) == 1
    assert findings[0].rule_id == "DS005"
    assert findings[0].status == FindingStatus.CONFIRMED
    assert findings[0].doc_fact["problems"] == [
        {"type": "missing_required_arguments", "parameters": ["data_path"]}
    ]


def test_ds005_accepts_valid_call_and_skips_unpacking():
    code = PythonParser().parse(
        "def train(data_path, epochs=50):\n    pass\n",
        file_path="train.py",
    )
    docs = MarkdownParser().parse(
        '```python\ntrain("data.csv")\ntrain(*args, **kwargs)\n```\n',
        file_path="README.md",
    )

    assert CallSignatureRule().check(code, docs) == []
