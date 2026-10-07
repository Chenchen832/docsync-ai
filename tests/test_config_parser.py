from docsync_ai.parsers import ConfigParser, MarkdownParser


def test_parses_nested_json_keys():
    entities = ConfigParser().parse(
        '{"training": {"batch_size": 32, "enabled": true}}',
        format_name="json",
        file_path="config.json",
    )

    assert {item.qualified_name for item in entities} == {
        "training",
        "training.batch_size",
        "training.enabled",
    }


def test_parses_nested_toml_keys():
    entities = ConfigParser().parse(
        "[training]\nbatch_size = 32\nepochs = 50\n",
        format_name="toml",
        file_path="config.toml",
    )

    assert {item.qualified_name for item in entities} == {
        "training",
        "training.batch_size",
        "training.epochs",
    }


def test_parses_yaml_mapping_with_exact_lines():
    entities = ConfigParser().parse(
        "training:\n  batch_size: 32\n  enabled: true\n",
        format_name="yaml",
        file_path="config.yaml",
    )
    by_path = {item.qualified_name: item for item in entities}

    assert by_path["training.batch_size"].metadata["value"] == 32
    assert by_path["training.enabled"].metadata["value"] is True
    assert by_path["training.batch_size"].line_start == 2


def test_markdown_config_entities_only_come_from_explicit_fence():
    markdown = """The word training.batch should not be parsed.

```yaml
training:
  batch: 32
```
"""
    entities = MarkdownParser().parse(markdown, file_path="README.md")
    keys = [item for item in entities if item.entity_type == "config_key"]

    assert {item.name for item in keys} == {"training", "training.batch"}
    assert all(item.metadata["source_kind"] == "fenced_config_block" for item in keys)
