from src.comparator import service
from src.comparator.models import Comparison, ComparisonChange
from src.comparator.schemas import ChangeDraft, CompareResult, MatchResult
from src.documents import db
from src.documents.service import create_version, save_document


class FakeStructuredLLM:
    """Returns queued results in order; records prompts (same pattern as test_reviewer)."""

    def __init__(self, *results):
        self.results = list(results)
        self.prompts = []

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


NEW_TEXT = "Section 1. Term is 24 months. Section 2. Liability is capped at fees."
OLD_TEXT = "Section 1. Term is 12 months. Section 2. Liability is unlimited."


def _prior_doc(text=OLD_TEXT, filename="msa-2025.pdf"):
    doc = save_document(b"x", filename, source="upload")
    create_version(doc.id, text)
    return doc


def test_select_match_returns_none_when_no_other_documents():
    doc = save_document(b"x", "new.pdf", source="upload")
    matched_id, matched_text = service.select_match(doc.id, NEW_TEXT, llm=None)
    assert matched_id is None
    assert matched_text == ""


def test_select_match_picks_candidate_and_returns_its_text():
    prior = _prior_doc()
    doc = save_document(b"x", "msa-2026.pdf", source="upload")
    fake = FakeStructuredLLM(MatchResult(matched_document_id=prior.id, reason="same MSA"))
    matched_id, matched_text = service.select_match(doc.id, NEW_TEXT, llm=fake)
    assert matched_id == prior.id
    assert matched_text == OLD_TEXT
    # the prompt offered the candidate and the new document
    assert "msa-2025.pdf" in fake.prompts[0]
    assert "msa-2026.pdf" in fake.prompts[0]


def test_select_match_excludes_self_and_versionless_docs():
    no_version = save_document(b"x", "empty.pdf", source="upload")  # noqa: F841
    doc = save_document(b"x", "new.pdf", source="upload")
    create_version(doc.id, NEW_TEXT)  # its own version must not make it a candidate
    matched_id, matched_text = service.select_match(doc.id, NEW_TEXT, llm=None)
    assert matched_id is None
    assert matched_text == ""


def test_select_match_llm_none_answer_means_no_match():
    _prior_doc()
    doc = save_document(b"x", "new.pdf", source="upload")
    fake = FakeStructuredLLM(MatchResult(matched_document_id=None, reason="unrelated"))
    matched_id, matched_text = service.select_match(doc.id, NEW_TEXT, llm=fake)
    assert matched_id is None
    assert matched_text == ""


def test_select_match_hallucinated_id_means_no_match():
    _prior_doc()
    doc = save_document(b"x", "new.pdf", source="upload")
    fake = FakeStructuredLLM(MatchResult(matched_document_id=99999, reason="made up"))
    matched_id, matched_text = service.select_match(doc.id, NEW_TEXT, llm=fake)
    assert matched_id is None
    assert matched_text == ""


def _compare_result(*changes, summary="Liability and term changed."):
    return CompareResult(summary=summary, changes=list(changes))


def test_run_comparison_no_candidates_stores_no_match():
    doc = save_document(b"x", "new.pdf", source="upload")
    comparison = service.run_comparison(doc.id, NEW_TEXT, llm=None)
    assert comparison.status == "no_match"
    assert comparison.matched_document_id is None


def test_run_comparison_happy_path_persists_summary_and_valid_changes():
    prior = _prior_doc()
    doc = save_document(b"x", "new.pdf", source="upload")
    fake = FakeStructuredLLM(
        MatchResult(matched_document_id=prior.id, reason="same MSA"),
        _compare_result(
            ChangeDraft(kind="modified", clause="Term",
                        before_text="Term is 12 months.", after_text="Term is 24 months.",
                        note="Term doubled."),
            ChangeDraft(kind="added", clause="Fabricated",
                        before_text=None, after_text="text not present in the new document",
                        note="hallucinated"),
            ChangeDraft(kind="removed", clause="Also fabricated",
                        before_text="text not present in the old document", after_text=None,
                        note="hallucinated"),
        ),
    )
    comparison = service.run_comparison(doc.id, NEW_TEXT, llm=fake)
    assert comparison.status == "ready"
    assert comparison.matched_document_id == prior.id
    assert comparison.summary == "Liability and term changed."
    stored = service.get_comparison(doc.id)
    assert stored is not None
    _, changes = stored
    assert [c.clause for c in changes] == ["Term"]  # both fabricated anchors dropped
    # both texts reached the compare prompt
    assert NEW_TEXT in fake.prompts[1] and OLD_TEXT in fake.prompts[1]


def test_run_comparison_modified_requires_both_anchors():
    prior = _prior_doc()
    doc = save_document(b"x", "new.pdf", source="upload")
    fake = FakeStructuredLLM(
        MatchResult(matched_document_id=prior.id, reason="same"),
        _compare_result(
            ChangeDraft(kind="modified", clause="Half-anchored",
                        before_text="not in old text", after_text="Term is 24 months.",
                        note="before anchor bad"),
        ),
    )
    service.run_comparison(doc.id, NEW_TEXT, llm=fake)
    _, changes = service.get_comparison(doc.id)
    assert changes == []


def test_run_comparison_llm_failure_stores_failed_and_does_not_raise():
    _prior_doc()
    doc = save_document(b"x", "new.pdf", source="upload")
    fake = FakeStructuredLLM(RuntimeError("provider down"))
    comparison = service.run_comparison(doc.id, NEW_TEXT, llm=fake)
    assert comparison.status == "failed"
    stored, changes = service.get_comparison(doc.id)
    assert stored.status == "failed"
    assert changes == []


def test_get_comparison_returns_none_before_any_run():
    doc = save_document(b"x", "new.pdf", source="upload")
    assert service.get_comparison(doc.id) is None
