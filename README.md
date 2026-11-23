# SmartTask AI

SmartTask AI is a project and task management MVP with a React/Vite client, a Django REST API, JWT authentication, and three independently trained PyTorch prediction models.

## What works

- Register, sign in/out, refresh JWTs, and update your profile.
- Create, edit, and delete projects; set deadlines and track completion progress.
- Create, edit, assign, complete, filter, and delete tasks.
- Add existing accounts to owned projects and assign work to project members.
- Dashboard totals for projects, tasks, completion, pending work, overdue work, and project progress.
- Authenticated API predictions for task priority, completion duration, and project delay risk.
- Responsive React workspace with forms, loading/error states, and prediction panels.

## Run locally

Python 3.12, Node.js 20+, and npm are expected. From the repository root:

```bash
# Use the existing environment, or create it once if needed.
source .venv/bin/activate
python -m pip install -r requirements.txt

# Set a development-only secret in this shell (do not commit it).
export DJANGO_SECRET_KEY="$(openssl rand -base64 48)"
export DJANGO_DEBUG=true

cd backend
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:5173>, register an account, and create a project. SQLite is the local default. To use PostgreSQL, first create a database and set `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_PORT` before starting Django; the PostgreSQL driver is included in `requirements.txt`. For a local macOS socket-authenticated PostgreSQL install:

```bash
createdb smarttask_ai
export POSTGRES_DB=smarttask_ai
export POSTGRES_USER="$(whoami)"
export POSTGRES_HOST=
```

Keep `DJANGO_DEBUG=false` and provide a strong `DJANGO_SECRET_KEY` outside local development.

### Train the models

Model weights are deliberately excluded from Git. Generate them locally before using prediction endpoints:

```bash
# Optional but recommended: download the Apache-2.0 Jira issue data for priority training.
python deep_learning/download_dataset.py
python deep_learning/train_models.py
```

Training automatically uses MPS when available, otherwise CPU. If the public priority file is absent, the priority pipeline uses a labelled synthetic fallback. Completion-time and delay models currently use labelled synthetic examples. Dataset provenance, split sizes, holdout metrics, and figures are written to `deep_learning/experiments/`; model weights and downloaded/raw data remain ignored by Git.

## API overview

All application endpoints require a bearer access token except health, registration, and obtaining/refreshing tokens.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health/` | Health check |
| `POST /api/auth/register/` | Register and return JWTs |
| `POST /api/auth/token/` | Obtain JWT pair (`username` is the account email) |
| `POST /api/auth/token/refresh/` | Refresh access token |
| `POST /api/auth/logout/` | Blacklist a refresh token |
| `GET/PATCH /api/auth/me/` | Read/update profile |
| `GET/POST /api/projects/` | List/create projects |
| `GET/PATCH/DELETE /api/projects/{id}/` | Read/update/delete a project |
| `GET/POST /api/tasks/` | List/create tasks |
| `GET/PATCH/DELETE /api/tasks/{id}/` | Read/update/delete a task |
| `GET/POST /api/team/` | List collaborators/add a registered member to an owned project |
| `GET /api/dashboard/` | Dashboard statistics and summaries |
| `POST /api/predictions/priority/` | BiLSTM priority prediction |
| `POST /api/predictions/completion/` | MLP completion-days estimate |
| `POST /api/predictions/delay/` | Feedforward project-delivery forecast |

Set `VITE_API_URL` if the API is not at `http://127.0.0.1:8000/api`. Configure `CORS_ALLOWED_ORIGINS` when the browser client is served from a different origin.

## Checks

```bash
cd backend
python manage.py check
python manage.py test core
cd ../frontend
npm run build
npm audit
```

## Model evidence and limits

The priority classifier can use the public Jira dataset; completion and delay training is synthetic. Read [dataset provenance, preprocessing, evaluation, and caveats](documentation/ML_DATASET_AND_EVALUATION.md) before interpreting scores. Synthetic-data scores demonstrate that training and serving work; they are not claims of real-world accuracy or project-delay validity.

The access token is stored in browser session storage for this MVP. Use HTTPS, production-grade secret management, appropriate database backups, and a production deployment configuration before exposing it publicly.
