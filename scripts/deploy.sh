#!/bin/bash
# ═══════════════════════════════════════════════════════════
# NutriGenie — Simplified Deploy Script
# ═══════════════════════════════════════════════════════════
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="nutrigenie"

echo -e "${BLUE}═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}  NutriGenie — Deploy                  ║${NC}"
echo -e "${BLUE}═══════════════════════════════════════╝${NC}"

# ── Check prerequisites ──
echo -e "\n${YELLOW}[1/7] Checking prerequisites...${NC}"
for cmd in aws sam python3; do
    if ! command -v $cmd &>/dev/null; then echo -e "${RED}❌ $cmd not found${NC}"; exit 1; fi
done
aws sts get-caller-identity > /dev/null 2>&1 || { echo -e "${RED}❌ AWS not configured. Run: aws configure${NC}"; exit 1; }
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${GREEN}✅ AWS Account: ${ACCOUNT_ID} | Region: ${REGION}${NC}"

# ── Build numpy layer ──
echo -e "\n${YELLOW}[2/7] Building numpy Lambda layer...${NC}"
mkdir -p backend/layers/numpy/python
pip install numpy -t backend/layers/numpy/python --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 -q 2>/dev/null
echo -e "${GREEN}✅ Layer ready${NC}"

# ── SAM Build ──
echo -e "\n${YELLOW}[3/7] Building SAM application...${NC}"
sam build --region "$REGION"
echo -e "${GREEN}✅ Build complete${NC}"

# ── SAM Deploy ──
echo -e "\n${YELLOW}[4/7] Deploying to AWS (3-5 minutes)...${NC}"
sam deploy \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --capabilities CAPABILITY_IAM \
    --resolve-s3 \
    --no-confirm-changeset \
    --no-fail-on-empty-changeset
echo -e "${GREEN}✅ Deployed${NC}"

# ── Get outputs ──
echo -e "\n${YELLOW}[5/7] Getting endpoints...${NC}"
API_URL=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text --region "$REGION")
FRONTEND_URL=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='FrontendUrl'].OutputValue" --output text --region "$REGION")
DATA_BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='DataBucket'].OutputValue" --output text --region "$REGION")
echo -e "${GREEN}✅ API: ${API_URL}${NC}"

# ── Upload data to S3 ──
echo -e "\n${YELLOW}[6/7] Uploading data to S3...${NC}"
# Upload patient data
aws s3 cp iom_data.json "s3://${DATA_BUCKET}/patients/IOM_KIT001.json" --region "$REGION"
# Upload nutrition dataset
aws s3 cp backend/data/indian_nutrition_dataset.json "s3://${DATA_BUCKET}/nutrition/indian_nutrition_dataset.json" --region "$REGION"
echo -e "${GREEN}✅ Data uploaded${NC}"

# ── Deploy frontend ──
echo -e "\n${YELLOW}[7/7] Deploying frontend...${NC}"
sed -i "s|API_URL = ''|API_URL = '${API_URL}'|g" frontend/app.js
FRONTEND_BUCKET="nutrigenie-web-${ACCOUNT_ID}"
aws s3 sync frontend/ "s3://${FRONTEND_BUCKET}/" --region "$REGION" --delete
echo -e "${GREEN}✅ Frontend deployed${NC}"

# ── Done ──
echo -e "\n${BLUE}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  🎉 DEPLOYED SUCCESSFULLY! 🎉${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "\n📡 ${GREEN}API:${NC}      ${API_URL}"
echo -e "🌐 ${GREEN}Frontend:${NC} ${FRONTEND_URL}"
echo -e "\n${BLUE}Test with:${NC}"
echo -e "  curl ${API_URL}/patient/IOM_KIT001"
echo -e "  curl -X POST ${API_URL}/meal -d '{\"kit_id\":\"IOM_KIT001\"}'"
echo -e "\n${YELLOW}⚠️  Enable Bedrock models in AWS Console first!${NC}"
echo -e "   Bedrock → Model Access → Enable Claude 3 Haiku & Titan Embed V2"
