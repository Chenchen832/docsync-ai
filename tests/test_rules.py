import json

import pytest

from docsync_ai.models import FindingStatus
from docsync_ai.parsers import MarkdownParser, PythonParser
from docsync_ai.rules import DefaultValueRule, ParameterRule

CODE = "def train(data_path, epochs=50, batch_size=32):\n    pass\n"


def _entities(markdown: str):
    code = PythonParser().parse(CODE, file_path="train.py")
    docs = MarkdownParser().parse(markdown, file_path="README.md")
    return code, docs


def test_ds001_does_not_compare_literal_positional_argument_with_parameter_name():
    code, docs = _entities(
        """```python
train("data.csv", epochs=50)
```
"""
    )

    assert ParameterRule().check(code, docs) == []


def test_ds001_does_not_compare_local_variable_with_parameter_name():
    code, docs = _entities(
        """```python
x = "data.csv"
train(x, epochs=50)
```
"""
    )

    assert ParameterRule().check(code, docs) == []


def test_ds001_detects_unknown_keyword_argument():
    code, docs = _entities(
        """```python
train(path="data.csv", epochs=50)
```
"""
    )
    findings = ParameterRule().check(code, docs)

    assert len(findings) == 1
    assert findings[0].rule_id == "DS001"
    assert findings[0].issue_type == "PARAMETER_NAME_MISMATCH"
    assert findings[0].severity == "HIGH"
    assert findings[0].status == FindingStatus.CONFIRMED
    assert findings[0].doc_fact["documented_parameter"] == "path"
    assert findings[0].doc_fact["argument_kind"] == "keyword"


def test_ds001_accepts_explicit_parameter_list_as_candidate():
    code, docs = _entities(
        """## train

Parameters:
- path: training dataset
"""
    )
    findings = ParameterRule().check(code, docs)

    assert len(findings) == 1
    assert findings[0].rule_id == "DS001"
    assert findings[0].severity == "MEDIUM"
    assert findings[0].status == FindingStatus.NEEDS_SEMANTIC_REVIEW
    assert findings[0].metadata["requires_semantic_review"] is True


def test_ds002_does_not_treat_explicit_example_value_as_default():
    code, docs = _entities(
        """```python
train("data.csv", epochs=100)
```
"""
    )

    assert not [entity for entity in docs if entity.entity_type == "declared_default"]
    assert DefaultValueRule().check(code, docs) == []


def test_ds002_detects_explicit_default_declaration_and_serializes():
    code, docs = _entities("`epochs` 默认值为 `100`。\n")
    findings = DefaultValueRule().check(code, docs)

    assert len(findings) == 1
    assert findings[0].rule_id == "DS002"
    assert findings[0].issue_type == "DEFAULT_VALUE_MISMATCH"
    assert findings[0].code_fact["default_value"] == 50
    assert findings[0].doc_fact["default_value"] == 100
    json.dumps(findings[0].to_dict(), ensure_ascii=False)


def test_ds002_accepts_matching_default_declaration():
    code, docs = _entities("epochs default = 50\n")

    assert DefaultValueRule().check(code, docs) == []


def test_ds002_detects_parameter_table_default_declaration():
    code, docs = _entities(
        """| parameter | value |
| --- | --- |
| epochs | default: 100 |
"""
    )
    claim = next(entity for entity in docs if entity.entity_type == "declared_default")
    findings = DefaultValueRule().check(code, docs)

    assert claim.metadata["declaration_kind"] == "table"
    assert claim.metadata["default_value"] == 100
    assert len(findings) == 1
    assert findings[0].rule_id == "DS002"


@pytest.mark.parametrize(
    ("signature", "declaration"),
    [
        ('mode="fast"', 'mode default = "fast"'),
        ("enabled=True", "enabled default = true"),
        ("cache=None", "cache default = None"),
        ("epochs=50", "epochs default = 50"),
        ("ratio=0.5", "ratio default = 0.5"),
        ("layers=[32, 64]", "layers default = [32, 64]"),
    ],
)
def test_ds002_normalizes_supported_explicit_default_types(signature, declaration):
    source = f"def configure({signature}):\n    pass\n"
    code = PythonParser().parse(source, file_path="config.py")
    docs = MarkdownParser().parse(declaration, file_path="README.md")

    assert DefaultValueRule().check(code, docs) == []
