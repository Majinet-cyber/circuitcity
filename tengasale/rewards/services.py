import random
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import SpinConfig, SpinGrant, SpinReward, SpinWallet


TWOPLACES = Decimal("0.01")


class NoSpinsAvailable(Exception):
    pass


class SpinDisabled(Exception):
    pass


def get_spin_config():
    config, _ = SpinConfig.objects.get_or_create(pk=1)
    return config


@transaction.atomic
def award_spin_for_application(application, user):
    wallet, _ = SpinWallet.objects.select_for_update().get_or_create(user=user)
    _, created = SpinGrant.objects.get_or_create(application=application, user=user)
    if not created:
        return False

    wallet.available_spins += 1
    wallet.total_spins_earned += 1
    wallet.save(update_fields=["available_spins", "total_spins_earned"])
    return True


def current_week_start():
    now = timezone.localtime()
    start = now - timedelta(days=now.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def jackpot_count_this_week(config):
    return SpinReward.objects.filter(
        reward_tier=SpinReward.TIER_JACKPOT,
        amount=config.jackpot_amount,
        spin_date__gte=current_week_start(),
    ).count()


def reward_tier_for_amount(amount, config):
    if amount == config.jackpot_amount:
        return SpinReward.TIER_JACKPOT
    if amount >= Decimal("2500.00"):
        return SpinReward.TIER_MEDIUM
    return SpinReward.TIER_SMALL


def reward_pool(config):
    rewards = [
        Decimal("100.00"),
        Decimal("100.00"),
        Decimal("100.00"),
        Decimal("500.00"),
        Decimal("500.00"),
        Decimal("1000.00"),
        Decimal("1000.00"),
        Decimal("2500.00"),
        Decimal("5000.00"),
        Decimal("10000.00"),
    ]
    if jackpot_count_this_week(config) < config.jackpot_limit_per_week:
        rewards.append(config.jackpot_amount)
    return rewards


@transaction.atomic
def perform_spin(user, chooser=None):
    config = get_spin_config()
    if not config.is_enabled:
        raise SpinDisabled("Spin rewards are currently disabled.")

    wallet, _ = SpinWallet.objects.select_for_update().get_or_create(user=user)
    if wallet.available_spins <= 0:
        raise NoSpinsAvailable("No spins available.")

    # TODO: replace this MVP random picker with an auditable reward engine before production payouts.
    chooser = chooser or random.choice
    amount = Decimal(chooser(reward_pool(config))).quantize(TWOPLACES)
    if amount == config.jackpot_amount and jackpot_count_this_week(config) >= config.jackpot_limit_per_week:
        amount = Decimal("1000.00")

    wallet.available_spins -= 1
    wallet.total_spins_used += 1
    wallet.save(update_fields=["available_spins", "total_spins_used"])

    reward = SpinReward.objects.create(
        user=user,
        amount=amount,
        spin_date=timezone.now(),
        reward_tier=reward_tier_for_amount(amount, config),
    )
    return reward
