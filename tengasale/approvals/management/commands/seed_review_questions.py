"""
Management command: seed_review_questions

Seeds the ReviewQuestion model with TengaSale's required structured
questionnaire questions for each underwriter review stage.

Usage:
    python manage.py seed_review_questions
    python manage.py seed_review_questions --force   # overwrites existing
"""
from django.core.management.base import BaseCommand


QUESTIONS = [
    # ── Identity Check ──────────────────────────────────────────────────────
    {
        "stage": "identity",
        "question_key": "id_readable",
        "question_text": "Is the National ID readable?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": True,
        "risk_weight": 3,
        "order": 1,
    },
    {
        "stage": "identity",
        "question_key": "id_name_matches",
        "question_text": "Does the ID name match the application?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": True,
        "risk_weight": 3,
        "order": 2,
    },
    {
        "stage": "identity",
        "question_key": "selfie_matches_id",
        "question_text": "Does the selfie reasonably match the ID image?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": True,
        "risk_weight": 3,
        "order": 3,
    },
    {
        "stage": "identity",
        "question_key": "dob_plausible",
        "question_text": "Is the date of birth plausible?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": True,
        "risk_weight": 2,
        "order": 4,
    },
    {
        "stage": "identity",
        "question_key": "phone_confirmed",
        "question_text": "Is the phone number confirmed?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 5,
    },
    {
        "stage": "identity",
        "question_key": "identity_acceptable",
        "question_text": "Is the customer identity acceptable for approval?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": True,
        "risk_weight": 3,
        "order": 6,
    },

    # ── Address Check ───────────────────────────────────────────────────────
    {
        "stage": "address",
        "question_key": "address_neighbour_spoken",
        "question_text": "Did you speak to a neighbour or local contact?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 1,
    },
    {
        "stage": "address",
        "question_key": "address_contact_confirmed",
        "question_text": "Did the contact confirm the customer lives there?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 2,
    },
    {
        "stage": "address",
        "question_key": "address_locatable",
        "question_text": "Can TengaSale locate the customer if follow-up is required?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": True,
        "risk_weight": 3,
        "order": 3,
    },
    {
        "stage": "address",
        "question_key": "address_traceable",
        "question_text": "Is the location traceable enough for merchant/customer support?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 4,
    },
    {
        "stage": "address",
        "question_key": "address_acceptable",
        "question_text": "Is the address acceptable for approval?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": True,
        "risk_weight": 2,
        "order": 5,
    },

    # ── Customer Call ───────────────────────────────────────────────────────
    {
        "stage": "customer_call",
        "question_key": "customer_spoken",
        "question_text": "Did you speak with the customer?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": True,
        "risk_weight": 3,
        "order": 1,
    },
    {
        "stage": "customer_call",
        "question_key": "customer_intro_done",
        "question_text": "Did you introduce yourself as TengaSale?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 1,
        "order": 2,
    },
    {
        "stage": "customer_call",
        "question_key": "customer_confirmed_application",
        "question_text": "Did the customer confirm they applied for the phone?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": True,
        "risk_weight": 3,
        "order": 3,
    },
    {
        "stage": "customer_call",
        "question_key": "customer_understands_commitment",
        "question_text": "Does the customer understand they are making a legal commitment to repay?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": True,
        "risk_weight": 3,
        "order": 4,
    },
    {
        "stage": "customer_call",
        "question_key": "customer_understands_lock",
        "question_text": "Does the customer understand missed payments may affect device access where applicable?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 5,
    },
    {
        "stage": "customer_call",
        "question_key": "customer_understands_fraud_consequences",
        "question_text": "Does the customer understand tampering or fraudulent use may lead to action under the contract?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 6,
    },
    {
        "stage": "customer_call",
        "question_key": "customer_notified_recording",
        "question_text": "Was the customer notified that the call may be recorded for quality and compliance?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 1,
        "order": 7,
    },

    # ── Guarantor Call ──────────────────────────────────────────────────────
    {
        "stage": "guarantor_call",
        "question_key": "guarantor_spoken",
        "question_text": "Did you speak with the guarantor?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 1,
    },
    {
        "stage": "guarantor_call",
        "question_key": "guarantor_knows_customer",
        "question_text": "Did the guarantor confirm they know the customer?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": True,
        "risk_weight": 3,
        "order": 2,
    },
    {
        "stage": "guarantor_call",
        "question_key": "guarantor_confirmed_details",
        "question_text": "Did the guarantor confirm the customer's details?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 3,
    },
    {
        "stage": "guarantor_call",
        "question_key": "guarantor_confident_repayment",
        "question_text": "Is the guarantor confident the customer can pay?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 4,
    },
    {
        "stage": "guarantor_call",
        "question_key": "guarantor_notified_recording",
        "question_text": "Was the guarantor notified that the call may be recorded for quality and compliance?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 1,
        "order": 5,
    },

    # ── Employer / Income Call ──────────────────────────────────────────────
    {
        "stage": "employer_call",
        "question_key": "employer_spoken",
        "question_text": "Did you speak with the employer or income contact?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 1,
    },
    {
        "stage": "employer_call",
        "question_key": "employer_confirmed_income",
        "question_text": "Did they confirm the customer's work/income details?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 2,
    },
    {
        "stage": "employer_call",
        "question_key": "employer_confirmed_frequency",
        "question_text": "Did they confirm the customer's income frequency?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 3,
    },
    {
        "stage": "employer_call",
        "question_key": "employer_confident_repayment",
        "question_text": "Are they confident the customer can pay?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 4,
    },
    {
        "stage": "employer_call",
        "question_key": "employer_notified_recording",
        "question_text": "Was the contact notified that the call may be recorded for quality and compliance?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 1,
        "order": 5,
    },

    # ── Income Check ────────────────────────────────────────────────────────
    {
        "stage": "income",
        "question_key": "income_understood",
        "question_text": "Is the income source clearly understood?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 1,
    },
    {
        "stage": "income",
        "question_key": "income_dependable",
        "question_text": "Is the income source dependable / regular?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 3,
        "order": 2,
    },
    {
        "stage": "income",
        "question_key": "income_proof_reviewed",
        "question_text": "Has proof of income been reviewed?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": False,
        "risk_weight": 2,
        "order": 3,
    },
    {
        "stage": "income",
        "question_key": "income_affordability_ok",
        "question_text": "Is income sufficient relative to the repayment amount?",
        "answer_type": "yes_no",
        "required": True,
        "fail_if_no": True,
        "risk_weight": 3,
        "order": 4,
    },
]


class Command(BaseCommand):
    help = "Seed ReviewQuestion with TengaSale's structured questionnaire questions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Update existing questions with new text/settings.",
        )

    def handle(self, *args, **options):
        from approvals.models import ReviewQuestion

        force = options["force"]
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for q in QUESTIONS:
            obj, created = ReviewQuestion.objects.get_or_create(
                question_key=q["question_key"],
                defaults={
                    "stage": q["stage"],
                    "question_text": q["question_text"],
                    "answer_type": q["answer_type"],
                    "required": q["required"],
                    "fail_if_no": q["fail_if_no"],
                    "risk_weight": q["risk_weight"],
                    "order": q["order"],
                    "active": True,
                },
            )
            if created:
                created_count += 1
            elif force:
                obj.stage = q["stage"]
                obj.question_text = q["question_text"]
                obj.answer_type = q["answer_type"]
                obj.required = q["required"]
                obj.fail_if_no = q["fail_if_no"]
                obj.risk_weight = q["risk_weight"]
                obj.order = q["order"]
                obj.active = True
                obj.save()
                updated_count += 1
            else:
                skipped_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"ReviewQuestions: {created_count} created, {updated_count} updated, {skipped_count} skipped."
        ))
