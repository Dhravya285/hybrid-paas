# Hybrid PaaS

This project has:

- a `Next.js` frontend in `hbf-frontend`
- a `FastAPI` backend in `server`
- GitHub OAuth login
- repository browsing
- a deployment flow that clones a GitHub repo, builds a Docker image, and pushes it to Amazon ECR

The backend does not deploy to ECS, EKS, App Runner, or EC2 yet. It currently builds and pushes an image to ECR.

## Project flow

1. The frontend signs the user in with GitHub using NextAuth.
2. The frontend sends the GitHub access token to the backend.
3. The backend validates the token, stores the user in the database, and returns its own JWT.
4. The frontend uses that backend JWT to call protected backend routes.
5. When you deploy, the backend:
   - clones the selected GitHub repository and branch
   - detects a Next.js app in the selected source folder
   - uses the existing `Dockerfile`, or generates one if missing
   - builds the image locally with Docker
   - logs in to ECR with the local AWS CLI session
   - creates or reuses a per-project ECR repository under the configured base namespace
   - pushes the image to that project-specific ECR repository

## Prerequisites

Install these on the machine where you run the backend:

- Node.js 20+
- npm
- Python 3.11+
- PostgreSQL
- Git
- Docker Desktop or Docker Engine
- AWS CLI v2

You also need:

- a GitHub OAuth app
- an AWS account with ECR access

## Required configuration

### 1. GitHub OAuth app

Create an OAuth app in GitHub:

1. Go to GitHub `Settings -> Developer settings -> OAuth Apps`.
2. Click `New OAuth App`.
3. Use these local development values:
   - `Homepage URL`: `http://localhost:3000`
   - `Authorization callback URL`: `http://localhost:3000/api/auth/callback/github`
4. Copy the generated client ID and client secret.

## 2. Frontend environment

Create `hbf-frontend/.env.local` from `hbf-frontend/.env.example`.

```env
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=replace-with-a-long-random-string
CLIENT_ID=your_github_oauth_app_client_id
CLIENT_SECRET=your_github_oauth_app_client_secret
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_ECR_REPOSITORY_URI=945219712463.dkr.ecr.us-east-1.amazonaws.com/hybrid-paas
```

Notes:

- `CLIENT_ID` and `CLIENT_SECRET` are the exact variable names used by the current code.
- `NEXT_PUBLIC_API_BASE_URL` must point to the FastAPI server.
- `NEXT_PUBLIC_ECR_REPOSITORY_URI` is the base ECR namespace. A repo like `owner/app` is pushed to `.../hybrid-paas/owner/app`.

### 3. Backend environment

Create `server/.env` from `server/.env.example`.

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/hybrid_paas
JWT_SECRET=replace-with-a-long-random-string
JWT_EXPIRY_HOURS=24
DEFAULT_ECR_REPOSITORY_URI=945219712463.dkr.ecr.us-east-1.amazonaws.com/hybrid-paas
```

Notes:

- The backend reads `DATABASE_URL` through SQLAlchemy.
- The example above uses PostgreSQL with the `psycopg` driver.
- `JWT_SECRET` should be a long random value, not `dev-secret`.
- `DEFAULT_ECR_REPOSITORY_URI` is the backend base ECR namespace used to derive project-specific repositories.

### 4. Database

Create a PostgreSQL database named `hybrid_paas`.

Example with Docker:

```powershell
docker run --name hybrid-paas-postgres `
  -e POSTGRES_USER=postgres `
  -e POSTGRES_PASSWORD=postgres `
  -e POSTGRES_DB=hybrid_paas `
  -p 5432:5432 `
  -d postgres:16
```

The backend auto-creates tables on startup.

### 5. AWS credentials and ECR access

The backend executes `aws`, `docker`, and `git` locally. That means the backend host must already have:

- Docker running
- AWS CLI installed and authenticated
- permission to create ECR repositories if they do not exist
- permission to push images to ECR

Set up AWS CLI:

```powershell
aws configure
aws sts get-caller-identity
```

Minimum ECR permissions needed by this app:

- `ecr:GetAuthorizationToken`
- `ecr:DescribeRepositories`
- `ecr:CreateRepository`
- `ecr:BatchCheckLayerAvailability`
- `ecr:InitiateLayerUpload`
- `ecr:UploadLayerPart`
- `ecr:CompleteLayerUpload`
- `ecr:PutImage`
- `ecr:BatchGetImage`

## Install and run

### 1. Start the backend

Important: run the backend from the `server` directory. The current imports are written for that working directory.

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install fastapi "uvicorn[standard]" sqlalchemy python-dotenv requests "python-jose[cryptography]" "psycopg[binary]"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Verify it is up:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected response:

```json
{
  "message": "status running"
}
```

### 2. Start the frontend

Open a second terminal:

```powershell
cd hbf-frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## How to use the app

1. Sign in with GitHub.
2. After login, the frontend exchanges the GitHub token with the backend and stores the backend JWT in `localStorage`.
3. Open the repositories page.
4. Select a repository.
5. Choose:
   - branch
   - Next.js source folder
   - build command
   - run command
   - image tag, or keep the generated unique tag
   - AWS region if needed
6. Click `Deploy`. The app pushes the built image to a project-specific repository under the configured base ECR namespace.

```text
Base namespace:
945219712463.dkr.ecr.us-east-1.amazonaws.com/hybrid-paas

Example final repository for `DilipSC/tally-temp`:
945219712463.dkr.ecr.us-east-1.amazonaws.com/hybrid-paas/dilipsc/tally-temp
```

## Assumptions in the current code

- The frontend is expected at `http://localhost:3000`.
- The backend is expected at `http://localhost:8000`.
- Backend CORS currently allows only:
  - `http://localhost:3000`
  - `http://127.0.0.1:3000`
- Deployment currently supports only `Next.js` source folders.
- If the selected source folder does not contain a `Dockerfile`, the backend generates one.
- The deploy UI computes a per-project ECR repository from the configured base namespace.
- If no custom tag is supplied, the deploy flow generates a unique tag from branch name and timestamp instead of reusing `latest`.
- Default commands for a standard Next.js app are:
  - build: `npm run build`
  - run: `npm start`

If you change ports or origins, update both:

- `hbf-frontend/.env.local`
- `server/main.py`

## Troubleshooting

### `Required command not found in PATH`

Install the missing local dependency on the backend machine:

- `git`
- `docker`
- `aws`

### `Invalid GitHub token`

- confirm your GitHub OAuth app callback URL is exactly `http://localhost:3000/api/auth/callback/github`
- confirm `CLIENT_ID` and `CLIENT_SECRET` are correct
- sign out and sign in again

### `Backend auth token not found. Sign in again.`

- the backend JWT was not stored in the browser
- open the home page again and sign in once more
- make sure the backend is reachable at `NEXT_PUBLIC_API_BASE_URL`

### Database connection errors

- confirm PostgreSQL is running
- confirm `DATABASE_URL` is correct
- confirm the Python PostgreSQL driver was installed

### ECR login or push failures

- run `aws sts get-caller-identity` and make sure it works
- confirm the chosen AWS region matches the ECR URI
- confirm Docker is running before starting a deploy

## Files added for setup

- `README.md`
- `hbf-frontend/.env.example`
- `server/.env.example`

These files are the quickest way to bootstrap the project locally.
