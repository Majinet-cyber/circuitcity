# Generated migration for AgentMilestone model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tenants', '0001_initial'),  # Adjust if needed
    ]

    operations = [
        migrations.CreateModel(
            name='AgentMilestone',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('milestone_type', models.CharField(max_length=50)),
                ('milestone_name', models.CharField(max_length=100)),
                ('milestone_emoji', models.CharField(default='⭐', max_length=10)),
                ('sales_count', models.IntegerField(default=0)),
                ('achieved_at', models.DateTimeField(auto_now_add=True)),
                ('year', models.IntegerField(blank=True, null=True)),
                ('month', models.IntegerField(blank=True, null=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_milestones', to='tenants.business')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='milestones', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-achieved_at'],
            },
        ),
        migrations.AddIndex(
            model_name='agentmilestone',
            index=models.Index(fields=['user', 'business'], name='hq_agentmil_user_id_b17e89_idx'),
        ),
        migrations.AddIndex(
            model_name='agentmilestone',
            index=models.Index(fields=['business', 'year', 'month'], name='hq_agentmil_busines_44e1b5_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='agentmilestone',
            unique_together={('user', 'business', 'milestone_type', 'year', 'month')},
        ),
    ]

