"""
Run this locally to generate a password hash for a new user, then paste
the hash into auth_config.yaml. Never store plaintext passwords in the
config file — only the output of this script.

Usage:
    python app/utils/hash_password.py "TheirChosenPassword"
"""
import sys

import streamlit_authenticator as stauth

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: python app/utils/hash_password.py "TheirChosenPassword"')
        sys.exit(1)

    plain_password = sys.argv[1]
    hashed = stauth.Hasher.hash(plain_password)
    print("\nPaste this into auth_config.yaml as the user's `password:` value:\n")
    print(hashed)
    print()
