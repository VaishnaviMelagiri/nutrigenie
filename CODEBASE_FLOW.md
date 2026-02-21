# Codebase Flow: What Every File Does

This document outlines the exact flow of the NutriGenie application and explains the specific purpose of every single file in the repository.

---

## 1. The Core Infrastructure

### `template.yaml`
**What it does:** This is the most important file for the AWS backend. It acts as the "blueprint" for your entire infrastructure. When you run `sam deploy`, AWS reads this file to instantly build the API Gateway, the S3 Data Bucket, the DynamoDB Table, and all 3 Lambda Functions with the exact memory sizes and permissions needed.
**Flow:** CloudFormation > Provisions Infrastructure.

---

## 2. The Frontend Directory (`/frontend`)

This folder contains the complete website that patients interact with. It is hosted statically out of the `nutrigenie-web` S3 bucket.

### `frontend/index.html`
**What it does:** The visual structure of the website. It contains the Hero section, the input box for the Kit ID, and the empty container `<div>` that Javascript will eventually fill with generated meal cards.

### `frontend/styles.css`
**What it does:** The design language. It uses modern, high-contrast dark themes, subtle gradients, and CSS animations to make the meal cards fade in beautifully and feel like a premium mobile app.

### `frontend/app.js`
**What it does:** The brain of the frontend. 
**Flow:**
1. Triggers when the user clicks "Generate Meal Plan" or "Swap Meal".
2. Reads the `Kit ID` the user typed.
3. Automatically shows loading spinners.
4. Uses `fetch()` to send an HTTP POST request to the API Gateway using the `API_URL` variable to reach the cloud backend.
5. Receives the massive JSON response from the AI.
6. Translates that ugly JSON into beautiful HTML cards (Breakfast, Lunch, Dinner, etc.) and injects them onto the screen.

---

## 3. The Backend Serverless Functions (`/backend`)

The backend is completely serverless. It uses AWS Lambda functions to handle API requests. Unlike traditional servers, these files are only "awake" for the 5-15 seconds it takes to generate a meal plan.

### `/backend/lambdas/load_patient/lambda_function.py`
**What it does:** A lightweight, fast function designed solely for data retrieval.
**Flow:**
1. A user types `IOM_KIT001` and the frontend queries this endpoint.
2. This Lambda instantly grabs `IOM_KIT001.json` out of the S3 database.
3. It parses the complicated clinical data and extracts exactly what the Frontend needs to show a quick "Patient Summary" on the screen before the AI starts generating the meals.

### `/backend/lambdas/generate_meal/lambda_function.py`
**What it does:** The heavy lifter. This file orchestrates the entire AI logic to generate a full 7-day meal plan.
**Flow:**
1. Receives the `Kit ID` from the API.
2. Connects to S3 to read the exact symptoms, allergies, and IBS subtype for that patient.
3. Performs a vector semantic search (RAG) against the Indian IFCT nutrition database to find compliant foods.
4. Constructs an enormous, highly complex "System Prompt" instructing Amazon Nova Micro exactly how to design a clinically accurate 7-day Indian meal plan that excludes specific allergens.
5. Invokes Amazon Bedrock to generate the plan.
6. Cross-references the AI's output with the nutrition database to inject precise calorie and macronutrient data.
7. Connects to DynamoDB and silently saves a permanent copy of the meal plan.
8. Returns the final JSON to the Frontend.

### `/backend/lambdas/swap_meal/lambda_function.py`
**What it does:** The precision editing tool. It regenerates exactly ONE meal if a patient dislikes it.
**Flow:**
1. Receives the specific meal details (e.g., "Lunch on Day 2") that the user hit the Swap button on.
2. Gathers the patient profile from S3 (to still enforce allergies).
3. Connects to Amazon Nova Micro and instructs it to swap the meal while respecting the exact same calorie/protein targets as the rejected food.
4. Returns just that one new meal card to the Frontend to seamlessly replace the old one in the UI.

---

## 4. Documentation & Handover

### `ARCHITECTURE.md`
**What it does:** A client-friendly explanation of why we used Serverless (S3, API Gateway, Lambda, DynamoDB) to achieve zero idle costs ($0/month) and perfect scalability, and explains how data is temporarily generated rather than permanently hoarded.

### `HANDOVER.md`
**What it does:** The exact, step-by-step terminal instructions for the IOM Bioworks engineering team to execute to completely transfer the code and deploy identical AWS infrastructure to their own corporate accounts.

### `README.md`
**What it does:** The professional front page of the GitHub repository. It acts as a billboard for the project, explaining the tech stack, the AI logic, and providing a clean index to the other documentation files.
