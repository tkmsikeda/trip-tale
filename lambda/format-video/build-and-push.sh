#!/bin/bash

set -euo pipefail

AWS_ACCOUNT_ID=${1:-547599937180}
AWS_REGION=${2:-ap-northeast-1}
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
LOCAL_IMAGE_NAME="format-video-lambda"
REMOTE_IMAGE_NAME="${ECR_REGISTRY}/home-video/formatter:latest"

echo "AWS Account: ${AWS_ACCOUNT_ID}"
echo "Region: ${AWS_REGION}"
echo "ECR Registry: ${ECR_REGISTRY}"

echo "Logging in to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

echo "Building Docker image..."
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \
  --output=type=docker \
  -t "${LOCAL_IMAGE_NAME}" \
  .

echo "Tagging image..."
docker tag "${LOCAL_IMAGE_NAME}:latest" "${REMOTE_IMAGE_NAME}"

echo "Pushing image..."
docker push "${REMOTE_IMAGE_NAME}"

echo "✅ Build, tag and push completed: ${REMOTE_IMAGE_NAME}"
