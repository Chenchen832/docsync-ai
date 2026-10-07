import json

from docsync_ai.parsers import PythonParser

SOURCE = '''
import argparse

def train(data_path, epochs=50, batch_size=32, *, options=None):
    """Train a model."""
    return data_path

async def fetch(url, retries=[1, 2]):
    return url

class Trainer:
    def fit(self, data, config={"fast": True}):
        return data

def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--batch-size", type=int, default=32)
    return parser
'''


def test_extracts_functions_methods_parameters_and_defaults():
    entities = PythonParser().parse(SOURCE, file_path="sample.py")
    by_name = {entity.name: entity for entity in entities}

    train = by_name["train"]
    assert train.entity_type == "function"
    assert train.qualified_name == "sample.train"
    assert train.parameters == ["data_path", "epochs", "batch_size", "options"]
    assert train.default_values == {"epochs": 50, "batch_size": 32, "options": None}
    assert train.description == "Train a model."

    assert by_name["fetch"].entity_type == "async_function"
    assert by_name["fetch"].default_values["retries"] == [1, 2]
    assert by_name["fit"].entity_type == "method"
    assert by_name["fit"].qualified_name == "sample.Trainer.fit"
    assert by_name["fit"].default_values["config"] == {"fast": True}


def test_extracts_argparse_and_is_json_serializable():
    entities = PythonParser().parse(SOURCE, file_path="sample.py")
    cli = next(entity for entity in entities if entity.entity_type == "cli_argument")

    assert cli.name == "--batch-size"
    assert cli.default_values == {"--batch-size": 32}
    assert cli.metadata["option_strings"] == ["-b", "--batch-size"]
    assert cli.line_start > 0
    assert cli.line_end >= cli.line_start
    json.dumps([entity.to_dict() for entity in entities])


def test_unsafe_default_expression_is_never_evaluated():
    entities = PythonParser().parse("def f(value=make_value()):\n    pass\n", file_path="x.py")
    function = next(entity for entity in entities if entity.name == "f")
    assert function.default_values["value"] == "make_value()"
