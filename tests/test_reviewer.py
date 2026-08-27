from src.classifier.schemas import ClassificationResult  # noqa: F401  (shared fake pattern)
from src.documents.service import latest_version, save_document, get_document
from src.reviewer import service
from src.reviewer.schemas import ReviewResult, SuggestionDraft


class FakeStructuredLLM:
    def __init__(self, result):
        self.result = result
        self.prompts = []

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.result


DOC_TEXT = (
    "Section 1. Term. This agreement lasts 12 months. "
    "Section 2. Liability. Liability is unlimited. "
    "Section 3. Notices. Notices go to legal@acme.com."
)


def _drafts(*pairs):
    return ReviewResult(suggestions=[
        SuggestionDraft(clause=c, original_text=o, replacement_text=r, rationale="why")
        for c, o, r in pairs
    ])


def test_run_review_persists_unique_anchors_and_marks_ready():
    doc = save_document(b"x", "msa.pdf", source="upload")
    fake = FakeStructuredLLM(_drafts(
        ("Section 2", "Liability is unlimited.", "Liability is capped at fees paid."),
        ("Bogus", "text that is not in the document", "irrelevant"),
        ("Dup", "Section", "occurs many times so must be dropped"),
    ))
    suggestions = service.run_review(doc.id, DOC_TEXT, llm=fake)
    assert [s.clause for s in suggestions] == ["Section 2"]
    assert suggestions[0].status == "pending"
    assert DOC_TEXT in fake.prompts[0]
    assert latest_version(doc.id).text_content == DOC_TEXT  # v1 created
    assert get_document(doc.id).review_ready_at is not None


def test_run_review_zero_suggestions_still_marks_ready():
    doc = save_document(b"x", "msa.pdf", source="upload")
    fake = FakeStructuredLLM(_drafts())
    assert service.run_review(doc.id, DOC_TEXT, llm=fake) == []
    assert get_document(doc.id).review_ready_at is not None
