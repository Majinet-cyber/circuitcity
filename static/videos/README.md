# Landing page demo video

Place the Emajinet Farm product demo video here:

- **Filename:** `emajinet-farm.mp4`
- **Full path:** `static/videos/emajinet-farm.mp4`
- **Referenced on:** Home/landing page in the "Watch Emajinet in action" section.

The template uses `{% static 'videos/emajinet-farm.mp4' %}`, so after adding the file run:

```bash
python manage.py collectstatic --noinput
```

(in production; in development Django serves from `static/` automatically.)

If the file is missing, the video area will show the poster image; add `emajinet-farm.mp4` to enable playback.
