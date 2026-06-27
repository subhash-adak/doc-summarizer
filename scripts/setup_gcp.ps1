# One-shot GCP setup script for Windows (PowerShell).
# Run this once before starting the app.
# Prerequisites: gcloud CLI installed and authenticated.

$ErrorActionPreference = "Continue"

# Get project ID
$projectId = gcloud config get-value project
if ([string]::IsNullOrEmpty($projectId)) {
    Write-Error "No active GCP project found. Please run: gcloud config set project <PROJECT_ID>"
}

$location = "us-central1"
$saName = "doc-summarizer-sa"
$saEmail = "${saName}@${projectId}.iam.gserviceaccount.com"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " DocSummarizer - GCP Setup (Windows)" -ForegroundColor Cyan
Write-Host " Project : $projectId" -ForegroundColor Cyan
Write-Host " Location: $location" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Enable required APIs
Write-Host "-> Enabling APIs (this may take a minute)..." -ForegroundColor Yellow
gcloud services enable `
  aiplatform.googleapis.com `
  drive.googleapis.com `
  --project=$projectId

# 2. Create service account for Vertex AI
Write-Host "-> Creating service account: $saName" -ForegroundColor Yellow
try {
    gcloud iam service-accounts create $saName `
      --display-name="DocSummarizer Vertex AI Service Account" `
      --project=$projectId
} catch {
    Write-Host "  (already exists or skipping)" -ForegroundColor Gray
}

# 3. Grant Vertex AI User role
Write-Host "-> Granting Vertex AI User role..." -ForegroundColor Yellow
$maxRetries = 3
$retryCount = 0
$success = $false

while (-not $success -and $retryCount -lt $maxRetries) {
    # Run and suppress error stream on retry to keep logs clean
    $null = gcloud projects add-iam-policy-binding $projectId `
      --member="serviceAccount:${saEmail}" `
      --role="roles/aiplatform.user" `
      --quiet 2>$null
    
    if ($LastExitCode -eq 0) {
        $success = $true
    } else {
        $retryCount++
        if ($retryCount -lt $maxRetries) {
            Write-Host "  GCP IAM propagation is in progress. Waiting 5 seconds before retry ($retryCount/$maxRetries)..." -ForegroundColor Yellow
            Start-Sleep -Seconds 5
        } else {
            # Final try showing the raw error for troubleshooting
            gcloud projects add-iam-policy-binding $projectId `
              --member="serviceAccount:${saEmail}" `
              --role="roles/aiplatform.user" `
              --quiet
            Write-Error "Failed to grant Vertex AI User role after $maxRetries attempts."
        }
    }
}


# 4. Download service account key
if (!(Test-Path -Path "credentials")) {
    New-Item -ItemType Directory -Force -Path "credentials" | Out-Null
}
$keyPath = "credentials/vertex_sa.json"
Write-Host "-> Creating service account key at $keyPath ..." -ForegroundColor Yellow
gcloud iam service-accounts keys create $keyPath `
  --iam-account=$saEmail `
  --project=$projectId

Write-Host ""
Write-Host "[OK] Done. Service account key saved to: $keyPath" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Download OAuth2 credentials from GCP Console:"
Write-Host "     APIs & Services -> Credentials -> OAuth 2.0 Client IDs"
Write-Host "     Save as: credentials/oauth_credentials.json"
Write-Host ""
Write-Host "  2. Copy and edit the environment file:"
Write-Host "     Copy-Item .env.example .env"
Write-Host "     # Set GCP_PROJECT_ID=$projectId"
Write-Host ""
Write-Host "  3. Run the app:"
Write-Host "     uvicorn main:app --reload"

