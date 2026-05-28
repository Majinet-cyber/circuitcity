# Render Deployment

- Create a PostgreSQL database on Render named tengasale-db.
- Copy the Internal Database URL.
- Create a Render Web Service connected to the GitHub repo.
- Runtime: Python.
- Build command: bash build.sh
- Start command: gunicorn --chdir tengasale config.wsgi:application
- Environment variables:
  - SECRET_KEY=generated-secret-key
  - DEBUG=False
  - DATABASE_URL=Render internal PostgreSQL database URL
  - PYTHON_VERSION=3.12.13
  - DJANGO_SETTINGS_MODULE=config.settings
- After deployment, add custom domain:
  - tengasale.emajinet.africa
- Update DNS with Render's CNAME target.
- Redeploy.
- If 500 error happens, check Render logs first. Only temporarily set DEBUG=True while debugging, then immediately return it to False.
