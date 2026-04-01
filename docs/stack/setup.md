# Environment and Setup

This project uses Python (with a virtual environment) and several scripts for data extraction, classification, and mapping. Follow these steps to set up your environment:

## 1. Clone the Repository
```
git clone https://github.com/jeremychia/hokkien-mee.git
cd hokkien-mee
```

## 2. Set Up Python Environment
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # If requirements.txt exists
```

## 3. Secrets
- Place your secrets in `secrets/secrets.py` and `facebook_cookies.txt` as required by the scripts.

## 4. Running Scripts
- Use `run.sh` for common tasks or run individual scripts in the `extractor/` directory.

## 5. Output
- Results and generated files are stored in the `output/` directory.
