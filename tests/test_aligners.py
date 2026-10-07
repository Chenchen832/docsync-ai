from docsync_ai.aligners import EntityAligner, normalize_identifier, normalize_qualified_name
from docsync_ai.models import CodeEntity, DocEntity


def _code(entity_type, name, qualified_name=None):
    return CodeEntity(
        entity_type=entity_type,
        name=name,
        qualified_name=qualified_name or name,
        file_path="app.py",
        line_start=1,
        line_end=1,
    )


def _doc(entity_type, name):
    return DocEntity(
        entity_type=entity_type,
        name=name,
        text=name,
        file_path="README.md",
        line_start=1,
        line_end=1,
    )


def test_identifier_normalization_is_deterministic():
    assert normalize_identifier("--Batch-Size") == "batch_size"
    assert normalize_qualified_name("Trainer.Fit-Model") == "trainer.fit_model"


def test_aligner_prefers_exact_qualified_name():
    code = _code("function", "train", "trainer.train")
    doc = _doc("function_call", "trainer.train")

    alignment = EntityAligner().best_alignment(doc, [code])

    assert alignment.alignment_type == "exact_qualified_name"
    assert alignment.alignment_score == 1.0
    assert alignment.evidence


def test_aligner_matches_normalized_cli_name():
    code = _code("cli_argument", "--batch-size")
    doc = _doc("cli_argument", "--batch_size")

    alignment = EntityAligner().best_alignment(doc, [code])

    assert alignment.alignment_type == "normalized_cli_name"
    assert alignment.alignment_score == 0.95


def test_aligner_skips_ambiguous_equal_matches():
    first = _code("function", "train", "a.train")
    second = _code("function", "train", "b.train")
    doc = _doc("function_call", "train")

    assert EntityAligner().best_alignment(doc, [first, second]) is None
