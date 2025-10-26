from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

MODELS = [
    ('inventory', ['inventoryitem','product','location','inventoryaudit']),
    ('sales', ['sale']),
]

def perms_for(app_label, model, codes):
    ct = ContentType.objects.get(app_label=app_label, model=model)
    return Permission.objects.filter(content_type=ct, codename__in=[f'{c}_{model}' for c in codes])

class Command(BaseCommand):
    help = "Create V1 groups: Admin, Agent, Auditor with basic perms."

    def handle(self, *args, **opts):
        admin, _ = Group.objects.get_or_create(name='Admin')
        agent, _ = Group.objects.get_or_create(name='Agent')
        auditor, _ = Group.objects.get_or_create(name='Auditor')

        # Admin: all (view/add/change/delete)
        admin_perms = []
        for app, models in MODELS:
            for m in models:
                admin_perms += list(perms_for(app, m, ['view','add','change','delete']))
        admin.permissions.set(set(admin_perms))

        # Agent: view + (add InventoryItem for scan-in) + view/add Sale
        agent_perms = []
        agent_perms += list(perms_for('inventory','inventoryitem', ['view','add','change']))  # change needed to mark SOLD
        agent_perms += list(perms_for('inventory','product', ['view']))
        agent_perms += list(perms_for('inventory','location', ['view']))
        agent_perms += list(perms_for('sales','sale', ['view','add']))
        agent.permissions.set(set(agent_perms))

        # Auditor: view only
        auditor_perms = []
        for app, models in MODELS:
            for m in models:
                auditor_perms += list(perms_for(app, m, ['view']))
        auditor.permissions.set(set(auditor_perms))

        self.stdout.write(self.style.SUCCESS("V1 groups ready: Admin, Agent, Auditor"))


