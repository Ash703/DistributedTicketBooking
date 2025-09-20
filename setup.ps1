Write-Output ">>> Setting up virtual environment..."
python -m venv venv
.\venv\Scripts\Activate.ps1

Write-Output ">>> Upgrading pip..."
pip install --upgrade pip

Write-Output ">>> Installing requirements..."
if (Test-Path requirements.txt) {
    pip install -r requirements.txt
} else {
    Write-Output "No requirements.txt found. Skipping..."
}

Write-Output ">>> Setup complete. To activate environment: .\venv\Scripts\Activate.ps1"