from __future__ import annotations

from django.core.management.base import BaseCommand

from inventory.models_marketplace import MarketplaceListing
from inventory.services.marketplace_media import (
    is_supported_media_name,
    media_file_is_usable,
    normalize_marketplace_media_name,
)


class Command(BaseCommand):
    help = "Backfill marketplace listing primary media from existing gallery images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report repairs without saving changes.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Optional maximum number of listings to inspect.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]

        qs = (
            MarketplaceListing.objects.select_related("business")
            .prefetch_related("images")
            .order_by("id")
        )
        if limit:
            qs = qs[:limit]

        checked = 0
        repaired = 0
        normalized = 0
        skipped_valid = 0
        skipped_no_gallery = 0
        skipped_broken = 0

        for listing in qs:
            checked += 1
            media_name = normalize_marketplace_media_name(getattr(listing.media_file, "name", ""))

            if media_name and media_name != listing.media_file.name and is_supported_media_name(media_name):
                self._save_media_name(listing, media_name, dry_run)
                normalized += 1
                skipped_valid += 1
                self.stdout.write(
                    f"normalized listing={listing.id} media_file={listing.media_file.name!r} -> {media_name!r}"
                )
                continue

            if media_file_is_usable(listing.media_file):
                skipped_valid += 1
                continue

            gallery_image = self._first_valid_gallery_image(listing)
            if not gallery_image:
                if listing.images.exists():
                    skipped_broken += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"skipped listing={listing.id}: gallery exists but no supported image path found"
                        )
                    )
                else:
                    skipped_no_gallery += 1
                continue

            image_name = normalize_marketplace_media_name(gallery_image.image.name)
            self._save_media_name(listing, image_name, dry_run)
            repaired += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"repaired listing={listing.id}: media_file set from gallery image={gallery_image.id}"
                )
            )

        mode = "DRY RUN" if dry_run else "APPLIED"
        self.stdout.write("")
        self.stdout.write(f"Marketplace primary image backfill {mode}")
        self.stdout.write(f"Listings checked: {checked}")
        self.stdout.write(f"Listings repaired: {repaired}")
        self.stdout.write(f"Legacy paths normalized: {normalized}")
        self.stdout.write(f"Skipped with valid primary media: {skipped_valid}")
        self.stdout.write(f"Skipped with no gallery images: {skipped_no_gallery}")
        self.stdout.write(f"Skipped with broken/unsupported gallery images: {skipped_broken}")

    def _first_valid_gallery_image(self, listing):
        for image in listing.images.all():
            image_name = normalize_marketplace_media_name(getattr(image.image, "name", ""))
            if is_supported_media_name(image_name, image_only=True):
                return image
        return None

    def _save_media_name(self, listing, media_name: str, dry_run: bool) -> None:
        if dry_run:
            return
        listing.media_file.name = media_name
        listing.save(update_fields=["media_file", "updated_at"])
