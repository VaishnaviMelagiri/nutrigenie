<div align="center">
  <img src="https://ui-avatars.com/api/?name=NutriGenie&background=4f46e5&color=fff&size=100&rounded=true" alt="NutriGenie Logo">
  <h1>NutriGenie by IOM Bioworks</h1>
  <p><b>An AI-Powered, Serverless Personalized Meal Plan Generator</b></p>
</div>

<br/>

NutriGenie is a highly advanced, cloud-native application designed to generate dynamic, hyper-personalized Indian meal plans. It leverages cutting-edge Artificial Intelligence (Amazon Bedrock) and clinical microbiome logic to prescribe 7-day meal plans based on a patient's unique biological report, allergies, and gut health factors.

---

## ✨ Key Features

- 🧬 **Microbiome-Aware AI:** Automatically digests IOM patient reports (Allergies, IBS Subtypes, Caloric Goals) to generate 100% compliant weekly meal plans.
- 🥘 **Cultural Alignment:** Specifically filters and prioritizes ingredients locally available in Indian household kitchens using the official IFCT diet database.
- 🔄 **Smart "Swap Meal" Engine:** Users can reject a prescribed meal to instantly regenerate a nutritionally-equivalent alternative without using the same ingredients.
- ⚡ **Serverless Scale:** 100% Hosted on AWS Serverless architecture, ensuring zero idle server costs ($0/month) while remaining capable of auto-scaling to thousands of concurrent users instantly.
- 🔒 **Data Sovereignty:** All HIPAA-compliant data routing and AI generations occur strictly within the proprietary AWS environment. 

---

## 🛠️ Technology Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | Vanilla HTML, CSS, JavaScript | Lightning-fast static UI |
| **API Layer** | Amazon API Gateway | Secure routing and internet access point |
| **Compute** | AWS Lambda (Python 3.12) | Core backend application logic (Zero servers) |
| **Database** | Amazon S3 & DynamoDB | NoSQL storage for patient records and meal plan history |
| **Artificial Intelligence** | Amazon Bedrock (Nova Micro) | Retrieval-Augmented Generation (RAG) and LLM inference |

---

## 📚 Handover & Documentation

This repository contains everything needed for the IOM Bioworks Engineering Team to take full ownership of the application, source code, and infrastructure.

Please refer to the following dedicated manuals:

### 1. 🏗️ [System Architecture Guide (`ARCHITECTURE.md`)](./ARCHITECTURE.md)
Read this document to understand exactly how data flows through the application, how the AI makes decisions, and why the AWS system was architected this way for maximum scalability and zero-maintenance.

### 2. 🚀 [Deployment & Handover Guide (`HANDOVER.md`)](./HANDOVER.md)
**IMPORTANT:** Start here. This step-by-step guide explains exactly how to deploy this exact backend infrastructure to the IOM Bioworks AWS Account, update the API URLs, and take full control over the Live Application and the DynamoDB Database.

---

## 📂 Repository Structure

```text
nutrigenie/
│
├── frontend/                  # Static website files (HTML, CSS, JS)
│   ├── index.html             # Main user interface
│   ├── app.js                 # API integrations and logic
│   └── styles.css             # Fluid, modern styling
│
├── backend/                   # AWS Lambda Backend Code
│   ├── lambdas/
│   │   ├── generate_meal/     # LLM logic for Weekly Plan Creation
│   │   ├── swap_meal/         # LLM logic for specific Meal Swapping
│   │   └── load_patient/      # API logic for fetching profile data
│   │
│   └── layers/                # Lambda execution layers (e.g., numpy)
│
├── patients/                  # Example JSON IOM Patient Reports
├── template.yaml              # AWS SAM Infrastructure as Code (IaC) Blueprint
├── ARCHITECTURE.md            # In-depth infrastructure mapping
├── HANDOVER.md                # Deployment and ownership transfer guide
└── README.md                  # This file
```

---
<div align="center">
  <i>Built exclusively on the Amazon Web Services (AWS) Cloud.</i>
</div>
