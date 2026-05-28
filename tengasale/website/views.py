"""Website views — public-facing pages for /site/."""
import os
from django.shortcuts import render, redirect


def landing(request):
    return render(request, "website/landing.html", {})


def about(request):
    return render(request, "website/landing.html", {"section": "about"})


def how_it_works(request):
    return render(request, "website/landing.html", {"section": "how_it_works"})


def merchants(request):
    return render(request, "website/landing.html", {"section": "merchants"})


def customers(request):
    return render(request, "website/landing.html", {"section": "customers"})


def faq(request):
    return render(request, "website/landing.html", {"section": "faq"})


def contact(request):
    return render(request, "website/landing.html", {"section": "contact"})


def terms(request):
    return render(request, "website/terms.html", {})


def privacy(request):
    return render(request, "website/privacy.html", {})


def payment_terms(request):
    return render(request, "website/payment_terms.html", {})


def merchant_terms(request):
    return render(request, "website/merchant_terms.html", {})


MALAWI_DISTRICTS = [
    "Balaka", "Blantyre", "Chikwawa", "Chiradzulu", "Chitipa",
    "Dedza", "Dowa", "Karonga", "Kasungu", "Likoma",
    "Lilongwe", "Machinga", "Mangochi", "Mchinji", "Mulanje",
    "Mwanza", "Mzimba", "Mzuzu", "Neno", "Nkhata Bay",
    "Nkhotakota", "Nsanje", "Ntcheu", "Ntchisi", "Phalombe",
    "Rumphi", "Salima", "Thyolo", "Zomba",
]


def merchant_signup(request):
    from .models import MerchantLead

    if request.method == "POST":
        data = request.POST
        errors = []

        business_name = data.get("business_name", "").strip()
        owner_full_name = data.get("owner_full_name", "").strip()
        phone = data.get("phone", "").strip()
        district = data.get("district", "").strip()
        business_type = data.get("business_type", "").strip()

        if not business_name:
            errors.append("Business name is required.")
        if not owner_full_name:
            errors.append("Owner full name is required.")
        if not phone:
            errors.append("Phone number is required.")
        if not district:
            errors.append("District is required.")
        if not business_type:
            errors.append("Business type is required.")

        if not errors:
            reg_raw = data.get("has_business_registration", "")
            has_reg = True if reg_raw == "yes" else (False if reg_raw == "no" else None)

            try:
                monthly_sales = int(data.get("estimated_monthly_phone_sales") or 0)
            except (ValueError, TypeError):
                monthly_sales = 0

            MerchantLead.objects.create(
                business_name=business_name,
                owner_full_name=owner_full_name,
                phone=phone,
                whatsapp_phone=data.get("whatsapp_phone", "").strip(),
                email=data.get("email", "").strip(),
                district=district,
                area=data.get("area", "").strip(),
                business_type=business_type,
                estimated_monthly_phone_sales=monthly_sales,
                has_business_registration=has_reg,
                preferred_payout_method=data.get("preferred_payout_method", "").strip(),
                message=data.get("message", "").strip(),
                source="public_site",
            )
            return redirect("website_merchant_signup_success")

        return render(request, "website/merchant_signup.html", {
            "errors": errors,
            "post": data,
            "districts": MALAWI_DISTRICTS,
        })

    return render(request, "website/merchant_signup.html", {"districts": MALAWI_DISTRICTS})


def merchant_signup_success(request):
    return render(request, "website/merchant_signup_success.html", {})


def careers(request):
    from .models import CareerLead

    if request.method == "POST":
        data = request.POST
        files = request.FILES
        errors = []

        full_name = data.get("full_name", "").strip()
        phone = data.get("phone", "").strip()
        district = data.get("district", "").strip()
        role_interested = data.get("role_interested", "").strip()

        if not full_name:
            errors.append("Full name is required.")
        if not phone:
            errors.append("Phone number is required.")
        if not district:
            errors.append("District is required.")
        if not role_interested:
            errors.append("Please select a role you are interested in.")

        cv = files.get("cv_file")
        if cv:
            ext = os.path.splitext(cv.name)[1].lower()
            if ext not in (".pdf", ".doc", ".docx"):
                errors.append("CV must be a PDF or Word document (.pdf, .doc, .docx).")
            elif cv.size > 5 * 1024 * 1024:
                errors.append("CV file must be under 5 MB.")

        if not errors:
            lead = CareerLead(
                full_name=full_name,
                phone=phone,
                email=data.get("email", "").strip(),
                district=district,
                role_interested=role_interested,
                note=data.get("note", "").strip(),
            )
            if cv:
                lead.cv_file = cv
            lead.save()
            return redirect("website_careers_success")

        return render(request, "website/careers.html", {
            "errors": errors,
            "post": data,
            "districts": MALAWI_DISTRICTS,
        })

    return render(request, "website/careers.html", {"districts": MALAWI_DISTRICTS})


def careers_success(request):
    return render(request, "website/careers_success.html", {})
