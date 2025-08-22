from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()

def ensure_group(name: str) -> Group:
    g, _ = Group.objects.get_or_create(name=name)
    return g

class Command(BaseCommand):
    help = "Create initial admin and sample agent users for beta"

    def handle(self, *args, **kwargs):
        # Ensure groups exist (you also have bootstrap_v1_roles; this is idempotent)
        admin_g = ensure_group("Admin")
        agent_g = ensure_group("Agent")
        auditor_g = ensure_group("Auditor")

        # Admin (from env for safety)
        import os
        an = os.environ.get("ADMIN_USERNAME", "admin")
        ae = os.environ.get("ADMIN_EMAIL", "admin@example.com")
        ap = os.environ.get("ADMIN_PASSWORD", "changeme123")

        admin, created = User.objects.get_or_create(username=an, defaults={"email": ae, "is_staff": True, "is_superuser": True})
        if created:
            admin.set_password(ap)
            admin.save()
            self.stdout.write(self.style.SUCCESS(f"Created superuser {an}"))
        else:
            self.stdout.write("Superuser exists")

        # Sample agents
        samples = [
            ("agent1", "agent1@example.com", os.environ.get("AGENT1_PASSWORD", "Agent1!pass")),
            ("agent2", "agent2@example.com", os.environ.get("AGENT2_PASSWORD", "Agent2!pass")),
            ("agent3", "agent3@example.com", os.environ.get("AGENT3_PASSWORD", "Agent3!pass")),
        ]
        for uname, email, pw in samples:
            u, created = User.objects.get_or_create(username=uname, defaults={"email": email})
            if created:
                u.set_password(pw)
                u.is_staff = False
                u.save()
                u.groups.add(agent_g)
                self.stdout.write(self.style.SUCCESS(f"Created agent {uname}"))
            else:
                self.stdout.write(f"Agent {uname} exists")
