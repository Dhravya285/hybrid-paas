# 🚀 Hybrid Cloud PaaS (Vercel-like Platform)

A scalable **Platform-as-a-Service (PaaS)** backend that enables users to connect repositories, configure builds, and automatically deploy applications using an event-driven CI/CD pipeline on AWS.

---

## 🌟 Features

* 🔗 Git repository integration (GitLab)
* ⚙️ Custom build & deployment configuration
* 🐳 Docker-based build system
* 📦 Container registry with AWS ECR
* ⚡ Event-driven deployment (ECR → EventBridge → Lambda → ECS)
* 🚀 Serverless container deployment using ECS Fargate
* 🔐 JWT-based authentication
* 📊 Deployment tracking & logs
* 🧱 Infrastructure as Code (Terraform / CloudFormation)

---

## 🏗️ Architecture Overview

```
User Push → GitLab CI/CD → Docker Build → ECR Push
     ↓
EventBridge → Lambda → ECS Service Update → Deployment 🚀
```

---

## 📁 Project Structure

```
paas-backend/
├── app/
│   ├── main.py
│   ├── api/v1/
│   │   ├── router.py
│   │   └── endpoints/
│   ├── core/
│   ├── models/
│   ├── schemas/
│   └── services/
├── terraform/
├── gitlab-ci/
├── scripts/
└── tests/
```

---

## ⚙️ Tech Stack

### Backend

* FastAPI
* Async SQLAlchemy
* PostgreSQL
* Pydantic

### Cloud & DevOps

* AWS ECR (Container Registry)
* AWS ECS Fargate (Deployment)
* AWS Lambda (Automation)
* AWS EventBridge (Triggers)
* Terraform / CloudFormation (IaC)

### CI/CD

* GitLab CI/CD
* Docker

---

## 🚀 Getting Started

### 1️⃣ Clone Repository

```bash
git clone https://github.com/your-username/paas-backend.git
cd paas-backend
```

---

### 2️⃣ Setup Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

---

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 4️⃣ Setup Environment Variables

Create `.env`:

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/paas
SECRET_KEY=your_secret
AWS_ACCESS_KEY_ID=xxxx
AWS_SECRET_ACCESS_KEY=xxxx
AWS_REGION=ap-south-1
GITLAB_TOKEN=your_token
```

---

### 5️⃣ Run Migrations

```bash
alembic upgrade head
```

---

### 6️⃣ Start Server

```bash
uvicorn app.main:app --reload
```

👉 API Docs: http://127.0.0.1:8000/docs

---

## 🔁 Deployment Flow

1. User connects Git repo
2. GitLab CI builds Docker image
3. Image pushed to AWS ECR
4. ECR triggers EventBridge
5. EventBridge triggers Lambda
6. Lambda updates ECS service
7. ECS deploys new version

---

## 🧪 Testing

```bash
pytest tests/
```

---

## ☁️ AWS Setup (High-Level)

* Create ECR repository
* Setup ECS cluster (Fargate)
* Configure EventBridge rule
* Create Lambda for deployment trigger
* Provision infrastructure using Terraform

---

## 📌 API Modules

* **Auth** → Login/Register (JWT)
* **Projects** → Manage apps & configs
* **Deployments** → Trigger & track deploys
* **Webhooks** → GitLab + AWS events
* **ECR** → Manage container images

---

## 🔥 Future Enhancements

* 🌐 Custom domains (Route53 + ALB)
* 🔄 Preview deployments (per branch)
* 📊 Deployment logs dashboard
* 🔁 Rollbacks & versioning
* ⚡ Build caching

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch
3. Commit changes
4. Open a pull request

---



