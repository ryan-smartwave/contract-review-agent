from src.comparator import service
from src.comparator.schemas import ChangeDraft, CompareResult, MatchResult
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
