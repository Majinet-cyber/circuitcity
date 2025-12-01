# support/admin.py
from django.contrib import admin
from .models import Ticket, TicketComment


class TicketCommentInline(admin.TabularInline):
    model = TicketComment
    extra = 1
    fields = ('author', 'comment', 'is_internal', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('reference', 'subject', 'business', 'creator', 'status', 'priority', 'created_at')
    list_filter = ('status', 'priority', 'created_at')
    search_fields = ('reference', 'subject', 'description', 'business__name')
    readonly_fields = ('reference', 'created_at', 'updated_at', 'resolved_at')
    inlines = [TicketCommentInline]
    
    fieldsets = (
        (None, {
            'fields': ('reference', 'business', 'creator', 'subject', 'description')
        }),
        ('Status', {
            'fields': ('status', 'priority', 'assigned_to', 'resolved_by', 'resolved_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'author', 'created_at', 'is_internal')
    list_filter = ('is_internal', 'created_at')
    search_fields = ('ticket__reference', 'comment')

