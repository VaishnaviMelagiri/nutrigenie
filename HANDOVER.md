# Handover Guide: NutriGenie by IOM Bioworks

This guide explains how to take full ownership of the Personalized Meal Plan Generator (NutriGenie). The application code is hosted on GitHub, and the backend infrastructure is hosted on AWS.

## 1. Codebase Handover (GitHub)

The current developer has the code on their personal GitHub account. To transfer this to the company:

### Option A: Transfer Repository Ownership (Recommended)
1. The developer goes to the repository on GitHub.
2. Go to **Settings** > **General** > Scroll down to the "Danger Zone".
3. Click **Transfer ownership**.
4. Enter the company's GitHub Organization name or the new owner's username.
5. The new owner will receive an email to accept the transfer. Once accepted, the repo URL will automatically redirect, and the company will own all code and commit history.

### Option B: The Company Forks or Clones the Repo
1. The company logs into their GitHub account.
2. The company creates a new, blank repository (e.g., `iom-bioworks/nutrigenie`).
3. Have the developer run the following in their terminal to push the code to the new repo:
   ```bash
   git remote set-url origin https://github.com/company-name/nutrigenie.git
   git push -u origin main
   ```

---

## 2. Infrastructure Handover (AWS)

Currently, the serverless backend (Lambdas, API Gateway, S3, DynamoDB) is deployed to the developer's personal AWS account using AWS SAM. 

To transfer the hosting to the company's AWS account, the company **must deploy the stack themselves**. AWS resources cannot be easily "transferred" between accounts, but deploying the identical stack on a new account takes less than 5 minutes.

### Step-by-Step Deployment for the Company

**Prerequisites for the Company:**
1. An AWS Account with Administrator access.
2. [AWS CLI installed](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) and configured (`aws configure`) with their Access Keys.
3. [AWS SAM CLI installed](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html).

**Deployment Steps:**
1. **Clone the code:**
   ```bash
   git clone https://github.com/your-new-repo/nutrigenie.git
   cd nutrigenie
   ```

2. **Build the Application:**
   ```bash
   sam build --region us-east-1
   ```

3. **Deploy to the Company AWS Account:**
   ```bash
   sam deploy --guided
   ```
   *Follow the prompts and accept the defaults. This will create identical Lambda functions, S3 buckets, and API Gateways on the company's AWS account.*

4. **Update the Frontend API URL:**
   Once the SAM deployment finishes, it will output a new `ApiUrl` (e.g., `https://xxxx.execute-api.us-east-1.amazonaws.com/prod`).
   * Overwrite `API_URL` in `frontend/app.js` with this new URL.

5. **Deploy the Frontend to the New S3 Bucket:**
   SAM will also output a new S3 bucket named `nutrigenie-web-xxxxx`. The company just needs to sync the frontend files to it:
   ```bash
   aws s3 sync frontend/ s3://nutrigenie-web-xxxxx/ --region us-east-1 --delete
   ```

6. **Migrate Patient Data:**
   The developer needs to give the company the `patients/` folder containing the JSON reports (or the company can download them and upload them to their new S3 Data Bucket created by SAM).

---

## 3. Final Verification

1. The company opens their unique Frontend URL (provided in the SAM deploy outputs).
2. Enter a test Kit ID (e.g., `IOM_KIT001`).
3. Click "Generate Meal Plan". If it works, the handover is 100% complete.

At this point, the developer can safely run `sam delete` on their personal machine to delete everything from their personal AWS account to avoid any future charges.
