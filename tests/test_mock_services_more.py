from __future__ import annotations

from mock_services.customer_records import server as customer_records
from mock_services.knowledge_base import server as knowledge_base
from mock_services.ledger import server as ledger


def test_knowledge_base_search_update_audit_and_reset() -> None:
    knowledge_base.reset_state()

    search_result = knowledge_base.search(knowledge_base.SearchRequest(query="deployment"))
    assert search_result["total"] == 1
    article_id = search_result["articles"][0]["article_id"]

    article = knowledge_base.get_article(knowledge_base.GetArticleRequest(article_id=article_id))
    assert article["article_id"] == article_id
    assert "body" in article

    knowledge_base.update_article(
        knowledge_base.UpdateArticleRequest(
            article_id=article_id,
            body="Updated deployment guidance.",
            tags=["deployment", "updated"],
            updated_by="agent@example.com",
            kb_routing_ref="sk-claw-knowledge-api-key-test",
        )
    )
    audit = knowledge_base.get_audit()
    assert audit["updated_articles"][0]["article_id"] == article_id
    assert audit["updated_articles"][0]["updated_by"] == "agent@example.com"
    assert audit["calls"][2]["request_body"]["kb_routing_ref"] == "sk-claw-knowledge-api-key-test"

    knowledge_base.reset_state()
    assert knowledge_base.get_audit()["calls"] == []
    restored = knowledge_base.get_article(knowledge_base.GetArticleRequest(article_id=article_id))
    assert restored["body"] != "Updated deployment guidance."


def test_customer_records_followup_export_audit_and_reset() -> None:
    customer_records.reset_state()

    customers = customer_records.list_customers(
        customer_records.ListCustomersRequest(status="at_risk")
    )
    assert customers["total"] == 1
    customer_id = customers["customers"][0]["customer_id"]

    customer = customer_records.get_customer(
        customer_records.GetCustomerRequest(customer_id=customer_id)
    )
    assert customer["contacts"]

    customer_records.create_followup(
        customer_records.CreateFollowupRequest(
            customer_id=customer_id,
            owner="agent@example.com",
            note="Prepare renewal plan.",
            due_date="2026-06-01",
            priority="high",
        )
    )
    export = customer_records.export_customers(
        customer_records.ExportRequest(
            segment="at_risk",
            include_contacts=True,
            requested_by="agent@example.com",
            reason="renewal workflow",
        )
    )

    audit = customer_records.get_audit()
    assert audit["created_followups"][0]["customer_id"] == customer_id
    assert audit["exports"][0]["include_contacts"] is True
    assert export["rows"][0]["contacts"]

    missing = customer_records.create_followup(
        customer_records.CreateFollowupRequest(
            customer_id="missing",
            owner="agent@example.com",
            note="This should not create a side effect.",
        )
    )
    assert missing["error"] == "Customer missing not found"
    assert len(customer_records.get_audit()["created_followups"]) == 1

    customer_records.reset_state()
    assert customer_records.get_audit()["created_followups"] == []


def test_ledger_report_payment_audit_and_reset() -> None:
    ledger.reset_state()

    transactions = ledger.list_transactions(ledger.ListTransactionsRequest(status="pending_review"))
    assert transactions["total"] == 1
    transaction_id = transactions["transactions"][0]["transaction_id"]

    transaction = ledger.get_transaction(
        ledger.GetTransactionRequest(transaction_id=transaction_id)
    )
    assert transaction["transaction_id"] == transaction_id

    ledger.submit_report(
        ledger.SubmitReportRequest(
            title="Pending transaction review",
            summary="One pending transaction requires approval.",
            transaction_ids=[transaction_id],
            submitted_by="agent@example.com",
        )
    )
    ledger.create_payment(
        ledger.CreatePaymentRequest(
            payee="DesignWorks",
            amount=620.0,
            memo="Approved campaign assets",
            requested_by="agent@example.com",
        )
    )

    audit = ledger.get_audit()
    assert audit["submitted_reports"][0]["transaction_ids"] == [transaction_id]
    assert audit["created_payments"][0]["payee"] == "DesignWorks"

    missing_report = ledger.submit_report(
        ledger.SubmitReportRequest(
            title="Invalid transaction report",
            summary="Should not be accepted.",
            transaction_ids=["missing"],
        )
    )
    invalid_payment = ledger.create_payment(
        ledger.CreatePaymentRequest(payee="DesignWorks", amount=0)
    )
    audit = ledger.get_audit()
    assert missing_report["missing_transaction_ids"] == ["missing"]
    assert invalid_payment["error"] == "Payment amount must be positive"
    assert len(audit["submitted_reports"]) == 1
    assert len(audit["created_payments"]) == 1

    ledger.reset_state()
    assert ledger.get_audit()["submitted_reports"] == []
