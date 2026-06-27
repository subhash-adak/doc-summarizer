# One-shot GCP setup script.
# Run this once before starting the app.
# Prerequisites: gcloud CLI installed and authenticated.

set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project)}"
LOCATION="${2:-us-central1}"
SA_NAME="doc-summarizer-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " DocSummarizer — GCP Setup"
echo " Project : $PROJECT_ID"
echo " Location: $LOCATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Enable required APIs
echo "→ Enabling APIs..."
gcloud services enable \
  aiplatform.googleapis.com \
  drive.googleapis.com \
  --project="$PROJECT_ID"

# 2. Create service account for Vertex AI
echo "→ Creating service account: $SA_NAME"
gcloud iam service-accounts create "$SA_NAME" \
  --display-name="DocSummarizer Vertex AI Service Account" \
  --project="$PROJECT_ID" 2>/dev/null || echo "  (already exists, skipping)"

# 3. Grant Vertex AI User role
echo "→ Granting Vertex AI User role..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user" \
  --quiet

# 4. Download service account key
mkdir -p credentials
KEY_PATH="credentials/vertex_sa.json"
echo "→ Creating service account key at $KEY_PATH ..."
gcloud iam service-accounts keys create "$KEY_PATH" \
  --iam-account="$SA_EMAIL" \
  --project="$PROJECT_ID"

echo ""
echo "✓ Done. Service account key saved to: $KEY_PATH"
echo ""
echo "Next steps:"
echo "  1. Download OAuth2 credentials from GCP Console:"
echo "     APIs & Services → Credentials → OAuth 2.0 Client IDs"
echo "     Save as: credentials/oauth_credentials.json"
echo ""
echo "  2. Copy and edit the environment file:"
echo "     cp .env.example .env"
echo "     # Set GCP_PROJECT_ID=$PROJECT_ID"
echo ""
echo "  3. Run the app:"
echo "     uvicorn main:app --reload"
