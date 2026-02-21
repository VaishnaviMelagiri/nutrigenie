# NutriGenie System Architecture & Application Flow

This document provides a high-level overview of the complete full-stack architecture for the Personalized Meal Plan Generator (NutriGenie). It explains how data flows through the system, how the database is handled, and why this specific serverless approach was chosen.

---

## 1. Database & Data Storage

### How are we handling the database?
Instead of a traditional relational database (like MySQL or PostgreSQL), the application leverages **Amazon S3 (Simple Storage Service)** as a NoSQL document database and blob store. This is extremely cost-effective, infinitely scalable, and simple to maintain.

There is a dedicated secure S3 bucket (`nutrigenie-data-*`) acting as the back-end database containing two folders:
1. `patients/`: Stores patient health profiles and microbiome reports as lightweight `.json` files (e.g., `IOM_KIT001.json`).
2. `nutrition_data/`: Stores the IFCT official Indian food database used by the AI.

### Are we storing the generated meal plans?
**No, meal plans are NOT permanently stored.** 
Meal plans are generated **on-the-fly (in real-time)** every time a user requests one. 
* **Why?** Generating on the fly ensures that the meal plan always uses the absolute latest AI models and up-to-date nutrition guidelines. Furthermore, not storing historical AI generations keeps database storage bloat at exactly zero, eliminating unnecessary cloud storage costs.

---

## 2. Complete Full-Stack Application Flow

When a user opens the app and enters their Kit ID, the following flow occurs in a matter of seconds.

### Step 1: The Frontend (Client-Side)
* **Tech Stack:** Vanilla HTML, CSS, JavaScript.
* **Hosting:** Hosted as a static website directly on an **Amazon S3 Website Bucket**. This means there is no traditional web server to maintain, and the site will never crash due to high traffic.
* **Action:** The user enters their Kit ID and clicks "Generate Meal Plan". The browser dispatches a secure HTTP POST request to the API.

### Step 2: The API Layer (Routing)
* **Tech Stack:** **Amazon API Gateway**
* **Action:** API Gateway receives the request. It acts as the secure front door to the backend, applying CORS rules and immediately routing the request to the correct backend function.

### Step 3: The Backend Logic (Compute)
* **Tech Stack:** **AWS Lambda (Python 3.12)**
* **Architecture:** *Serverless*. The backend functions "wake up", run the necessary code, and immediately shut down. There are zero idle server costs.
* **Action:** 
  1. The API triggers the `GenerateMealFunction` Lambda.
  2. The Lambda securely queries the S3 Database to fetch the patient's `IOM_KIT001.json` report.
  3. The Lambda extracts the user's dietary preferences, allergies, IBS subtypes, and microbiome goals.
  4. It then filters the IFCT Indian nutrition database to create a strict "Allowed/Avoid" list of ingredients.

### Step 4: Artificial Intelligence & Generation
* **Tech Stack:** **Amazon Bedrock (Nova Micro & Titan Embeddings)**
* **Action:** 
  1. **Retrieval-Augmented Generation (RAG):** The backend uses Titan Text Embeddings to securely semantic-search the nutrition dataset to find the most relevant, healthy foods for that specific patient's microbiome.
  2. **Generation:** All the patient data (allergies to avoid, foods to include) is passed to **Amazon Nova Micro** (a fast, highly intelligent LLM). 
  3. The LLM generates a complete 7-day Indian household meal plan adhering to strict calorie and macronutrient targets.

### Step 5: Delivery
* The completed JSON meal plan goes back through the API Gateway, is received by the Frontend, and is beautifully rendered on the screen into distinct daily meal cards.

---

## 3. The "Swap Meal" Flow
If a user dislikes a specific meal, they can click "Swap This Meal".
1. The Frontend sends the rejected meal and the user's patient profile via API Gateway to the `SwapMealFunction` Lambda.
2. The Lambda contacts Amazon Nova Micro exclusively to find a nutritional equivalent for that exact meal slot (e.g., matching the 400 calories and 15g protein of the rejected meal) without using the same ingredients.
3. The new meal is returned and seamlessly animated into the user interface.

---

## 4. Why This Architecture? (Benefits to the Client)

- **Cost-Efficiency:** Because everything uses Serverless technology (S3, API Gateway, Lambda, Bedrock), the infrastructure costs essentially **$0/month** while traffic is low. You only pay for exact milliseconds of compute time used.
- **Auto-Scaling:** If 10,000 customers request meal plans at the exact same second, AWS Lambda will instinctively spin up 10,000 concurrent, parallel backend instances. No manual server scaling required.
- **Zero Maintenance:** There are no operating systems to patch, no servers to reboot, and no databases to manage. AWS manages all the underlying hardware.
- **Data Privacy:** All patient data, logs, and AI generations are siloed strictly within the company's AWS environment. No data is sent to external third parties (like OpenAI), ensuring perfect HIPAA/compliance alignment.
