from docsync_ai.parsers import MarkdownParser

MARKDOWN = """# Training

Use `train` to start. `epochs` 默认值为 `100`。

```python
train(path, epochs=100, batch_size=64)
```

```bash
python app.py --batch-size 64
```
"""


def test_extracts_markdown_structure_and_locations():
    entities = MarkdownParser().parse(MARKDOWN, file_path="README.md")

    heading = next(entity for entity in entities if entity.entity_type == "heading")
    paragraph = next(entity for entity in entities if entity.entity_type == "paragraph")
    code_block = next(entity for entity in entities if entity.entity_type == "code_block")
    inline_names = [entity.name for entity in entities if entity.entity_type == "inline_code"]

    assert heading.name == "Training"
    assert heading.line_start == 1
    assert paragraph.line_start == 3
    assert code_block.line_start == 5
    assert code_block.line_end == 7
    assert {"train", "epochs", "100"}.issubset(inline_names)


def test_extracts_python_calls_cli_commands_and_default_claims():
    entities = MarkdownParser().parse(MARKDOWN, file_path="README.md")
    call = next(entity for entity in entities if entity.entity_type == "function_call")
    command = next(entity for entity in entities if entity.entity_type == "cli_command")
    cli_arg = next(entity for entity in entities if entity.entity_type == "cli_argument")
    default = next(entity for entity in entities if entity.entity_type == "declared_default")

    assert call.name == "train"
    assert call.line_start == 6
    assert call.metadata["keyword_parameters"] == ["epochs", "batch_size"]
    assert call.metadata["arguments"][0] == {
        "kind": "positional",
        "position": 0,
        "value": "path",
    }
    assert "positional_parameter_candidates" not in call.metadata
    assert command.line_start == 10
    assert cli_arg.name == "--batch-size"
    assert cli_arg.metadata["value"] == 64
    assert default.name == "epochs"
    assert default.metadata["default_value"] == 100
