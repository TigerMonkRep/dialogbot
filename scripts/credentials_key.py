"""Print a fresh CREDENTIALS_KEY: python -m scripts.credentials_key"""
from app.core.crypto import generate_key

if __name__ == "__main__":
    print(generate_key())
