from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from applications.models import FinancingApplication
from commissions.services import process_contract_completion

from .forms import ContractSignatureForm, ImeiForm, MerchantTermsForm
from .models import Contract


def can_access_contract_flow(user, application):
    return application.created_by_id == user.id or user.is_staff or user.is_superuser


@login_required
def contract_terms(request, app_id):
    application = get_object_or_404(
        FinancingApplication.objects.select_related("created_by", "deal"),
        id=app_id,
    )
    if not can_access_contract_flow(request.user, application):
        raise PermissionDenied
    if application.status not in ["approved", "contract_terms", "contract_signature"]:
        return redirect(application.get_continue_url())

    contract, _ = Contract.from_application(application)

    if request.method == "POST":
        form = MerchantTermsForm(request.POST)
        if form.is_valid():
            contract.terms_accepted_by_merchant = True
            contract.status = Contract.STATUS_TERMS_ACCEPTED
            contract.save(update_fields=["terms_accepted_by_merchant", "status", "updated_at"])
            application.status = "contract_signature"
            application.save(update_fields=["status"])
            return redirect("contract_signature", contract_id=contract.id)
    else:
        form = MerchantTermsForm()

    return render(request, "contracts/terms.html", {"application": application, "contract": contract, "form": form})


@login_required
def contract_signature(request, contract_id):
    contract = get_object_or_404(Contract.objects.select_related("application", "merchant"), id=contract_id)
    application = contract.application
    if not can_access_contract_flow(request.user, application):
        raise PermissionDenied

    if request.method == "POST":
        form = ContractSignatureForm(request.POST, instance=contract)
        if form.is_valid():
            contract = form.save(commit=False)
            contract.customer_contract_signature.save(form.signature_file.name, form.signature_file, save=False)
            contract.customer_terms_accepted = True
            contract.status = Contract.STATUS_SIGNED
            contract.save()
            application.status = "imei_entry"
            application.save(update_fields=["status"])
            return redirect("contract_imei", contract_id=contract.id)
    else:
        form = ContractSignatureForm(instance=contract)

    return render(request, "contracts/signature.html", {"contract": contract, "application": application, "form": form})


@login_required
def contract_imei(request, contract_id):
    contract = get_object_or_404(Contract.objects.select_related("application"), id=contract_id)
    application = contract.application
    if not can_access_contract_flow(request.user, application):
        raise PermissionDenied

    if request.method == "POST":
        form = ImeiForm(request.POST, instance=contract)
        if form.is_valid():
            contract = form.save(commit=False)
            contract.status = Contract.STATUS_IMEI_ENTERED
            contract.save()
            application.imei_number = contract.imei_number
            application.status = "contract_creating"
            application.save(update_fields=["imei_number", "status"])
            return redirect("contract_progress", contract_id=contract.id)
    else:
        form = ImeiForm(instance=contract)

    return render(request, "contracts/imei.html", {"contract": contract, "application": application, "form": form})


@login_required
def contract_progress(request, contract_id):
    contract = get_object_or_404(Contract.objects.select_related("application"), id=contract_id)
    application = contract.application
    if not can_access_contract_flow(request.user, application):
        raise PermissionDenied

    if contract.status == Contract.STATUS_IMEI_ENTERED:
        contract.status = Contract.STATUS_CONTRACT_CREATED
        contract.save(update_fields=["status", "updated_at"])
        application.status = "warranty_check"
        application.save(update_fields=["status"])

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "warranty":
            contract.warranty_checked = True
            contract.status = Contract.STATUS_WARRANTY_CHECKED
            contract.save(update_fields=["warranty_checked", "status", "updated_at"])
            application.status = "locking"
            application.save(update_fields=["status"])
            messages.success(request, "Warranty marked checked.")
        elif action == "locked":
            # TODO: replace this placeholder with Upya device locking once integration is available.
            contract.phone_locked = True
            contract.status = Contract.STATUS_LOCKED
            contract.save(update_fields=["phone_locked", "status", "updated_at"])
            application.status = "deposit_pending"
            application.save(update_fields=["status"])
            messages.success(request, "Phone marked locked.")
        elif action == "deposit":
            # TODO: replace this placeholder with deposit payment verification once integration is available.
            contract.deposit_paid = True
            contract.status = Contract.STATUS_COMPLETE
            contract.save(update_fields=["deposit_paid", "status", "updated_at"])
            application.status = "contract_complete"
            application.save(update_fields=["status"])
            process_contract_completion(application)
            return redirect("contract_complete", contract_id=contract.id)

        return redirect("contract_progress", contract_id=contract.id)

    return render(request, "contracts/progress.html", {"contract": contract, "application": application})


@login_required
def contract_complete(request, contract_id):
    contract = get_object_or_404(Contract.objects.select_related("application"), id=contract_id)
    if not can_access_contract_flow(request.user, contract.application):
        raise PermissionDenied
    return render(request, "contracts/complete.html", {"contract": contract, "application": contract.application})


@login_required
def contract_detail(request, contract_id):
    contract = get_object_or_404(Contract.objects.select_related("application", "merchant"), id=contract_id)
    if not can_access_contract_flow(request.user, contract.application):
        raise PermissionDenied
    return render(request, "contracts/detail.html", {"contract": contract, "application": contract.application})

# Create your views here.
