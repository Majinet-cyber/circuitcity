from django.template import TemplateDoesNotExist
from django.http import HttpResponse
from django.shortcuts import render
from django.middleware.csrf import get_token

def safe_render(request, template_name, ctx):
    try:
        return render(request, template_name, ctx)
    except TemplateDoesNotExist:
        csrf = get_token(request)
        return HttpResponse(
            f"<!doctype html><meta charset='utf-8'>"
            f"<div style='font-family:system-ui;padding:16px'>"
            f"<h2>Temporary page</h2>"
            f"<p>Template <code>{template_name}</code> missing.</p>"
            f"</div>",
            content_type="text/html; charset=utf-8",
        )
