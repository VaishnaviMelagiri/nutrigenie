# 🧬 NutriGenie — Personalized Indian Meal Plan Generator

> AI-powered meal plan generator that processes IOM gut health reports and creates personalized 7-day Indian household meal plans using AWS serverless + RAG.

---

## 📋 What This App Does

1. **You enter your Kit ID** (each customer has a unique kit ID)
2. **You upload your IOM patient report** (PDF)
3. **The system automatically extracts** your avoid list, reduce list, recommendations, and bacterial history
4. **AI generates a 7-day Indian meal plan** tailored to YOUR constraints
5. **Don't like a meal?** Click "Replace" to get a nutritionally similar alternative
6. **Everything is validated** against the Indian Government's IFCT nutrition database

---

## 🏗️ PHASE 1 — Folder Structure

```
meal-plan-generator/
├── backend/
│   ├── lambdas/
│   │   ├── upload_report/          ← Handles PDF upload
│   │   │   └── lambda_function.py
│   │   ├── extract_report/         ← OCR + AI extraction
│   │   │   └── lambda_function.py
│   │   ├── generate_embeddings/    ← Creates vector embeddings
│   │   │   └── lambda_function.py
│   │   ├── generate_meal_plan/     ← RAG + AI meal generation
│   │   │   └── lambda_function.py
│   │   ├── get_alternatives/       ← Replacement meal generation
│   │   │   └── lambda_function.py
│   │   ├── get_profile/            ← Fetch patient profile
│   │   │   └── lambda_function.py
│   │   └── get_plan/               ← Fetch current meal plan
│   │       └── lambda_function.py
│   ├── layers/
│   │   └── numpy/                  ← Lambda Layer for numpy
│   ├── utils/
│   │   ├── config.py               ← All configuration in one place
│   │   ├── prompt_templates.py     ← AI prompts (hallucination control)
│   │   └── nutrition_validator.py  ← Validates meals against constraints
│   └── data/
│       └── indian_nutrition_dataset.json  ← 55+ Indian foods (IFCT data)
├── frontend/
│   ├── index.html                  ← Main web page
│   ├── style.css                   ← Dark theme styling
│   └── app.js                      ← Frontend logic
├── scripts/
│   ├── deploy.sh                   ← One-click deployment
│   └── seed_nutrition.py           ← Load nutrition data to DynamoDB
├── template.yaml                   ← AWS SAM infrastructure-as-code
├── requirements.txt
├── SYSTEM_ARCHITECTURE.md          ← Detailed system design
└── README.md                       ← You are here
```

**What each folder does:**
- **`backend/lambdas/`** — Each subfolder is one AWS Lambda function (a small program that runs in the cloud)
- **`backend/utils/`** — Shared code used by multiple Lambda functions
- **`backend/data/`** — The Indian nutrition database (55+ foods with calories, protein, etc.)
- **`frontend/`** — The website your users see and interact with
- **`scripts/`** — Helper scripts for deployment and data loading
- **`template.yaml`** — Tells AWS what infrastructure to create (databases, APIs, etc.)

---

## ☁️ PHASE 2 — AWS Setup (Step-by-Step)

### Prerequisites — Install These First

#### 1. Create an AWS Account (Free)
- Go to [aws.amazon.com](https://aws.amazon.com) → Click "Create an AWS Account"
- You get **12 months of Free Tier**
- Enter your credit card (you won't be charged, it's for identity verification)

#### 2. Install AWS CLI
```bash
# Linux
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Verify
aws --version
```

#### 3. Install SAM CLI
```bash
# Linux
wget https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-x86_64.zip
unzip aws-sam-cli-linux-x86_64.zip -d sam-installation
sudo ./sam-installation/install

# Verify
sam --version
```

#### 4. Install Python 3.12
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.12 python3-pip

# Verify
python3 --version
```

#### 5. Configure AWS Credentials
```bash
aws configure
```
It will ask for:
```
AWS Access Key ID:     ← From AWS Console → IAM → Users → Your User → Security Credentials
AWS Secret Access Key: ← Same place
Default region:        us-east-1
Default output format: json
```

#### 6. Enable Bedrock Model Access
This is **critical** — without this, the AI won't work:

1. Go to [AWS Console](https://console.aws.amazon.com)
2. Search for **"Bedrock"** in the search bar
3. Click **"Model access"** in the left sidebar
4. Click **"Manage model access"**
5. Enable these two models:
   - ✅ **Anthropic → Claude 3 Haiku** (the AI brain)
   - ✅ **Amazon → Titan Text Embeddings V2** (for vector search)
6. Click **"Save changes"** and wait ~5 minutes for approval

---

### AWS Services Used & Free Tier Limits

| Service | What It Does | Free Tier |
|---------|-------------|-----------|
| **Lambda** | Runs your code without servers | 1M requests/month |
| **API Gateway** | Creates web API endpoints | 1M calls/month |
| **S3** | Stores files (PDFs, website, vectors) | 5 GB storage |
| **DynamoDB** | Database for patient data & meals | 25 GB, 25 read/write units |
| **Textract** | Reads text from PDF reports | 1,000 pages/month |
| **Bedrock** | AI model for text generation | ~$0.25/1M input tokens |

**Estimated cost for 50 users/month: ~$0.16** (only Bedrock has a small charge)

---

## 🔧 PHASE 3 — Backend Code

### How Each Lambda Works

#### `upload_report` — Handles File Upload
**Trigger:** User clicks "Upload" on the website
**What it does:**
1. Receives the PDF file + Kit ID from the user
2. Validates it's a real PDF (< 10 MB)
3. Stores the PDF in S3 (cloud storage) at `{kit_id}/report.pdf`
4. Creates a patient record in DynamoDB with status `PENDING`

**API:** `POST /upload`
```json
{
  "kit_id": "KIT-2024-00142",
  "file_name": "report.pdf",
  "file_content_base64": "<base64 encoded PDF>"
}
```

#### `extract_report` — Reads and Parses the Report
**Trigger:** Automatically runs when a new PDF appears in S3
**What it does:**
1. Uses **Amazon Textract** (OCR) to read text from the PDF
2. Sends the text to **Claude 3 Haiku** with a strict extraction prompt
3. Extracts: avoid list, reduce list, recommendations, bacterial history
4. Has a **regex fallback** if the AI fails
5. Chunks the text into pieces for the vector database
6. Saves everything to DynamoDB
7. Triggers the embedding Lambda

#### `generate_embeddings` — Creates Searchable Vectors
**Trigger:** Called by extract_report after processing
**What it does:**
1. Takes the text chunks from the patient report
2. Converts each chunk into a **768-dimension vector** using Titan Embeddings
3. Stores vectors in a simple binary index file in S3
4. Also indexes the nutrition database (one-time setup)

**Why vectors?** They let us search for relevant information. "Find foods good for someone who can't eat gluten" becomes a math problem instead of keyword matching.

#### `generate_meal_plan` — The Main Meal Generator
**Trigger:** User clicks "Generate Meal Plan"
**What it does:**
1. Fetches patient profile from DynamoDB
2. **RAG Retrieval:** Searches patient vectors AND nutrition vectors for relevant info
3. Builds a carefully crafted prompt with strict rules
4. Calls **Claude 3 Haiku** to generate a 7-day meal plan
5. **Validates** the plan against nutrition constraints
6. If validation fails, retries with error feedback
7. Stores the plan in DynamoDB

**API:** `POST /generate`
```json
{
  "kit_id": "KIT-2024-00142"
}
```

#### `get_alternatives` — Replacement Meals
**Trigger:** User clicks "Replace" on a meal they don't like
**What it does:**
1. Gets the rejected meal's nutritional profile
2. Uses RAG to find similar but different foods
3. Generates ONE alternative meal that matches within ±10% calories
4. Updates the meal plan in DynamoDB

**API:** `POST /alternatives`
```json
{
  "kit_id": "KIT-2024-00142",
  "day": "day_1",
  "meal_type": "breakfast",
  "reason": "I don't like ragi"
}
```

#### `get_profile` — View Patient Data
**API:** `GET /profile/{kit_id}`

#### `get_plan` — View Current Meal Plan
**API:** `GET /plan/{kit_id}`

---

## 🧠 PHASE 4 — RAG Embedding Code

### What Is RAG?

**RAG = Retrieval-Augmented Generation**

Instead of asking the AI to "make up" a meal plan (which could hallucinate), we:
1. **Store** real nutrition data as vectors (embeddings)
2. **Search** for the most relevant foods based on patient constraints
3. **Feed** those real foods INTO the AI's prompt
4. The AI can only use **real, verified foods** from our database

### How Our RAG Pipeline Works

```
Patient Report → [Chunk Text] → [Generate Embeddings] → [Store in Index]
                                                              ↓
User Query → [Generate Query Embedding] → [Search Index] → [Top 10 Results]
                                                              ↓
                                          [Build Prompt with Real Data] → [AI Generates Plan]
```

### Key Design Decisions

| Decision | Why |
|----------|-----|
| **Custom binary index instead of FAISS library** | Keeps Lambda package small (< 50 MB), zero dependency issues |
| **Two separate indexes** (patient + nutrition) | Patient context for constraints, nutrition for food options |
| **Cosine similarity ≥ 0.5 threshold** | Filters out irrelevant results |
| **Top-K: 5 for patient, 10 for nutrition** | Enough context without exceeding token limits |
| **L2-normalized vectors** | Makes cosine similarity = dot product (faster) |

---

## 🍛 PHASE 5 — Meal Generation Code

### How the AI Generates Meals

1. **Fetch patient profile** (what they can/can't eat)
2. **RAG retrieval** (find relevant nutrition data)
3. **Build a 3-layer prompt:**
   - **System prompt:** "You are a certified nutritionist. Follow these STRICT rules..."
   - **Context:** Real patient data + real nutrition data from RAG
   - **User prompt:** "Generate a 7-day meal plan for this specific patient"
4. **Call Claude 3 Haiku** with temperature 0.3 (low creativity = more factual)
5. **Validate output** against constraints
6. **Retry once** if validation fails, including error details in the retry prompt

### Meal Plan Structure
Each day has **5 meals**: breakfast, mid-morning snack, lunch, evening snack, dinner.
Each meal includes:
- Exact ingredients with quantities in grams
- food_id linking back to IFCT database
- Calories, protein, carbs, fat, fiber
- Preparation time
- Tags (gluten-free, high-fiber, etc.)

---

## ✅ PHASE 6 — Nutrition Validation Logic

### What Gets Validated

| Check | Severity | What Happens |
|-------|----------|-------------|
| Food on avoid list used | 🔴 CRITICAL | Plan is rejected, AI retries |
| Food on reduce list used | 🟡 WARNING | Logged, quantity checked |
| food_id doesn't exist in IFCT | 🔴 HIGH | Food might be hallucinated |
| Allergen tag matches avoid list | 🔴 CRITICAL | Cross-reference catches hidden allergens |
| Daily calories below target | 🟠 MEDIUM | Flagged but not rejected |
| Daily protein below minimum | 🟠 MEDIUM | Flagged |
| Missing meal in a day | 🔴 HIGH | Plan incomplete |

### Scoring System
- Start at **100 points**
- CRITICAL violation: **-25 points**
- HIGH violation: **-15 points**
- MEDIUM violation: **-5 points**
- WARNING: **-2 points**
- Plan passes if score > 0 AND zero CRITICAL/HIGH violations

---

## 🌐 PHASE 7 — Frontend Code

### What the User Sees

1. **Landing page** — Hero section with "Get Started" button
2. **Upload section** — Kit ID input + drag-and-drop PDF upload
3. **Processing status** — 4-step progress indicator (uploading → OCR → analyzing → indexing)
4. **Profile view** — Shows extracted avoid/reduce/recommended lists and bacteria
5. **Meal plan view** — 7-day tab selector, each day shows 5 meals with full nutrition info
6. **Replace button** — Opens modal to reject a meal and get an alternative
7. **Nutrition summary** — Bar charts showing daily calories/protein/carbs/fat/fiber

### Technology
- **HTML/CSS/JS only** — No React, no npm, no build tools needed
- **Dark theme** with glassmorphism (frosted glass effect)
- **Responsive** — Works on mobile and desktop
- **Inter + Outfit** fonts from Google Fonts

### Setting Up the Frontend
After deployment, update `app.js` line 8 with your API URL:
```javascript
API_BASE_URL: 'https://xxxxx.execute-api.us-east-1.amazonaws.com/prod'
```

---

## 🚀 PHASE 8 — Deployment Steps

### Option A: One-Click Deploy (Recommended)

```bash
# Clone/download the project
cd "meal plan"

# Make the deploy script executable
chmod +x scripts/deploy.sh

# Run the full deployment
./scripts/deploy.sh
```

This single script will:
1. ✅ Check your AWS credentials
2. ✅ Build the numpy Lambda layer
3. ✅ Build all Lambda functions (SAM build)
4. ✅ Deploy everything to AWS (SAM deploy)
5. ✅ Upload the frontend to S3
6. ✅ Seed the nutrition database
7. ✅ Create nutrition embeddings
8. ✅ Print your API URL and Frontend URL

### Option B: Step-by-Step Deploy (For Learning)

#### Step 1: Build the Lambda Layer
```bash
# Create directory for numpy layer
mkdir -p backend/layers/numpy/python

# Install numpy for Lambda (Amazon Linux)
pip install numpy \
  -t backend/layers/numpy/python \
  --platform manylinux2014_x86_64 \
  --only-binary=:all: \
  --python-version 3.12
```

#### Step 2: Build with SAM
```bash
# This packages all your Lambda functions
sam build
```

#### Step 3: Deploy to AWS
```bash
# First time: this will ask you some questions
sam deploy --guided

# It will ask:
# Stack Name: nutrigenie
# Region: us-east-1
# Confirm changes: Y
# Allow IAM roles: Y
# Save config: Y
```

#### Step 4: Note your API URL
After deployment, SAM shows outputs:
```
Outputs:
  ApiUrl: https://abc123.execute-api.us-east-1.amazonaws.com/prod
  FrontendUrl: http://nutrigenie-frontend-123456789.s3-website-us-east-1.amazonaws.com
```

#### Step 5: Update Frontend
Edit `frontend/app.js`, set your API URL:
```javascript
API_BASE_URL: 'https://abc123.execute-api.us-east-1.amazonaws.com/prod'
```

#### Step 6: Upload Frontend to S3
```bash
aws s3 sync frontend/ s3://nutrigenie-frontend-YOUR_ACCOUNT_ID/ --delete
```

#### Step 7: Seed Nutrition Data
```bash
python scripts/seed_nutrition.py
```

#### Step 8: Index Nutrition Embeddings
```bash
aws lambda invoke \
  --function-name nutrigenie-generate-embeddings \
  --payload '{"action": "index_nutrition"}' \
  --cli-binary-format raw-in-base64-out \
  output.json
```

---

## 📡 API Reference

After deployment, your API will be at:
```
https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod
```

| Method | Endpoint | Description | Body |
|--------|----------|-------------|------|
| `POST` | `/upload` | Upload IOM PDF report | `{"kit_id": "KIT-001", "file_name": "report.pdf", "file_content_base64": "..."}` |
| `GET` | `/profile/{kit_id}` | Get extracted patient profile | — |
| `POST` | `/generate` | Generate 7-day meal plan | `{"kit_id": "KIT-001"}` |
| `POST` | `/alternatives` | Get alternative meal | `{"kit_id": "KIT-001", "day": "day_1", "meal_type": "breakfast"}` |
| `GET` | `/plan/{kit_id}` | Get active meal plan | — |

### Example: Test with curl

```bash
# 1. Upload a report (replace base64 with actual PDF)
curl -X POST https://YOUR_API/prod/upload \
  -H "Content-Type: application/json" \
  -d '{"kit_id": "TEST-001", "file_name": "test.pdf", "file_content_base64": "JVBERi0..."}'

# 2. Check profile (after processing completes)
curl https://YOUR_API/prod/profile/TEST-001

# 3. Generate meal plan
curl -X POST https://YOUR_API/prod/generate \
  -H "Content-Type: application/json" \
  -d '{"kit_id": "TEST-001"}'

# 4. Get alternative meal
curl -X POST https://YOUR_API/prod/alternatives \
  -H "Content-Type: application/json" \
  -d '{"kit_id": "TEST-001", "day": "day_1", "meal_type": "breakfast", "reason": "I dont like ragi"}'

# 5. Check meal plan
curl https://YOUR_API/prod/plan/TEST-001
```

---

## 🔐 How Kit ID Works

- Each customer gets a **unique Kit ID** (e.g., `KIT-2024-00142`)
- This Kit ID is provided by the IOM lab along with the report
- The Kit ID is used as the **primary key** in all database tables
- All data (profile, meals, vectors) is isolated per Kit ID
- One Kit ID = One patient = One personalized meal plan

```
Customer A: KIT-2024-00142 → Patient A's avoid list → Patient A's meals
Customer B: KIT-2024-00143 → Patient B's avoid list → Patient B's meals
Customer C: KIT-2024-00144 → Patient C's avoid list → Patient C's meals
```

---

## 💰 Free Tier Cost Breakdown

| Component | Monthly Usage (50 users) | Cost |
|-----------|-------------------------|------|
| Lambda invocations | ~5,000 | **$0.00** |
| API Gateway requests | ~5,000 | **$0.00** |
| S3 storage | ~500 MB | **$0.00** |
| DynamoDB reads/writes | ~10,000 | **$0.00** |
| Textract pages | ~50 | **$0.00** |
| CloudWatch logs | ~100 MB | **$0.00** |
| Bedrock Claude 3 Haiku | ~500K tokens | **~$0.15** |
| Bedrock Titan Embed V2 | ~50K tokens | **~$0.01** |
| **TOTAL** | | **~$0.16/month** |

---

## 📈 Scaling for the Future

| Scale | Users/Month | What to Add |
|-------|-------------|-------------|
| **Phase 1** (current) | 0–100 | Current architecture |
| **Phase 2** | 100–500 | Add DynamoDB caching, API Gateway cache |
| **Phase 3** | 500–2,000 | Replace custom index with OpenSearch, add SQS |
| **Phase 4** | 2,000+ | Multi-region, Cognito auth, Bedrock Knowledge Bases |

---

## 🧯 Troubleshooting

| Problem | Solution |
|---------|----------|
| `sam deploy` fails with "S3 bucket already exists" | Add your account ID suffix to bucket names |
| Bedrock returns "Access denied" | Enable model access in AWS Console → Bedrock → Model Access |
| Textract fails on your PDF | Ensure PDF has text (not just images), max 1 page for sync API |
| Lambda timeout (>120s) | Increase timeout in `template.yaml` |
| Frontend shows "API URL not configured" | Update `API_BASE_URL` in `frontend/app.js` |
| `ModuleNotFoundError: numpy` | Rebuild the lambda layer: `scripts/deploy.sh` |

---

## 🗑️ Cleanup (Delete Everything)

```bash
# Delete the CloudFormation stack (removes all AWS resources)
sam delete --stack-name nutrigenie --region us-east-1 --no-prompts

# This removes: all Lambdas, DynamoDB tables, S3 buckets, API Gateway
```

---

## 📜 License

This project is for educational and personal use. The nutrition data is based on publicly available IFCT (Indian Food Composition Tables) data.
