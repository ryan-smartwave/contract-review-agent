from src.classifier import service
from src.classifier.schemas import ClassificationResult
from src.documents.service import save_document


class FakeStructuredLLM:
    def __init__(self, result):
        self.result = result
        self.prompts = []

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.result


def test_classify_and_log_persists_decision():
    doc = save_document(b"x", "msa-v2.docx", source="email")
    fake = FakeStructuredLLM(ClassificationResult(
        is_contract_revision=True, confidence=0.93,
        reasoning="Subject mentions redlined MSA revision.",
    ))
    result = service.classify_and_log(
        doc.id, doc.filename, subject="Re: MSA v2 redlines", body="see attached", llm=fake,
    )
    assert result.is_contract_revision is True
    log = service.get_log(doc.id)
    assert log is not None and log.confidence == 0.93
    assert "msa-v2.docx" in fake.prompts[0]


def test_classify_negative_case():
    doc = save_document(b"x", "newsletter.pdf", source="email")
    fake = FakeStructuredLLM(ClassificationResult(
        is_contract_revision=False, confidence=0.98, reasoning="Marketing newsletter.",
    ))
    result = service.classify_and_log(doc.id, doc.filename, subject="August deals!", llm=fake)
    assert result.is_contract_revision is False


def test_upload_classification_prompt_has_no_email_fields():
    doc = save_document(b"x", "Apex_Draft.pdf", source="upload")
    fake = FakeStructuredLLM(ClassificationResult(
        is_contract_revision=True, confidence=0.9, reasoning="Draft filename.",
    ))
    service.classify_and_log(doc.id, doc.filename, source="upload", llm=fake)
    prompt = fake.prompts[0]
    assert "Apex_Draft.pdf" in prompt
    assert "Email" not in prompt
    assert "uploaded" in prompt


def test_email_classification_prompt_keeps_email_fields():
    doc = save_document(b"x", "msa.pdf", source="email")
    fake = FakeStructuredLLM(ClassificationResult(
        is_contract_revision=True, confidence=0.9, reasoning="ok",
    ))
    service.classify_and_log(doc.id, doc.filename, subject="Re: MSA", body="see attached", llm=fake)
    assert "Email subject: Re: MSA" in fake.prompts[0]


def test_prompt_includes_document_text_and_caps_body():
    doc = save_document(b"x", "renamed.pdf", source="email")
    fake = FakeStructuredLLM(ClassificationResult(
        is_contract_revision=False, confidence=0.9, reasoning="Newsletter content.",
    ))
    long_body = "b" * 3000
    service.classify_and_log(
        doc.id, doc.filename, subject="s", body=long_body,
        document_text="August Newsletter: our latest promos", llm=fake,
    )
    prompt = fake.prompts[0]
    assert "August Newsletter: our latest promos" in prompt
    assert "b" * 2000 in prompt
    assert "b" * 2001 not in prompt


def test_upload_prompt_includes_document_text():
    doc = save_document(b"x", "Apex_Draft.pdf", source="upload")
    fake = FakeStructuredLLM(ClassificationResult(
        is_contract_revision=True, confidence=0.9, reasoning="ok",
    ))
    service.classify_and_log(
        doc.id, doc.filename, source="upload",
        document_text="MASTER SERVICES AGREEMENT between Apex and Globe", llm=fake,
    )
    assert "MASTER SERVICES AGREEMENT" in fake.prompts[0]
