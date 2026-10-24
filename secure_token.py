"""
Portable bot-token encryption helper. Drop this file into the root of any
Discord bot with a plaintext JSON config file (config.json, env.json, etc.)
holding the bot token under a string field.

Usage:
    import secure_token
    bot.run(secure_token.secure_token())                              # config.json, field "token"
    bot.run(secure_token.secure_token(config_path="env.json"))        # different config filename
    bot.run(secure_token.secure_token(token_field="bottoken"))        # different field name

Key resolution, in order:
  1. The env var named by env_key_var (default RAFISOL_BOT_TOKEN_ENCRYPTION_KEY), if set.
     Keeps the key off disk entirely - export it at deploy time instead of
     committing/copying a key file. Preferred.
  2. A key file (default bot_token.key) alongside the config, auto-generated
     on first run if missing. Falls back to this when the env var isn't set,
     so this keeps working unchanged if you never opt into the env var.

Whatever key is active, the stored token is auto-upgraded to it: a raw
plaintext token gets encrypted, and a token still encrypted under the old
on-disk key gets decrypted with that key and re-encrypted under the active
one. Requires the `cryptography` package.
"""

import os
import json
from cryptography.fernet import Fernet

DEFAULT_KEY_FILE = "bot_token.key"
DEFAULT_ENV_KEY_VAR = "RAFISOL_BOT_TOKEN_ENCRYPTION_KEY"

def _load_or_create_key(key_file: str, env_key_var: str) -> bytes:
    if os.path.exists(key_file):
        with open(key_file, "rb") as f:
            return f.read().strip()
    key = Fernet.generate_key()
    with open(key_file, "wb") as f:
        f.write(key)
    try:
        os.chmod(key_file, 0o600)
    except Exception:
        pass
    print(f"Generated new encryption key at [{key_file}]. Set {env_key_var} instead to avoid keeping the key on disk at all.")
    return key

def _get_env_fernet(env_key_var: str):
    val = os.environ.get(env_key_var)
    return Fernet(val.encode("utf-8")) if val else None

def secure_token(config_path: str = "config.json", token_field: str = "token", key_file: str = DEFAULT_KEY_FILE, env_key_var: str = DEFAULT_ENV_KEY_VAR) -> str:
    with open(config_path, "r") as f:
        data = json.load(f)

    stored = data[token_field]
    env_fernet = _get_env_fernet(env_key_var)
    active = env_fernet or Fernet(_load_or_create_key(key_file, env_key_var))

    try:
        return active.decrypt(stored.encode("utf-8")).decode("utf-8") # already under the active key
    except Exception:
        pass

    # only worth trying the old on-disk key if the env key is what's active
    # now and a leftover key file exists (never create one just to check)
    if env_fernet is not None and os.path.exists(key_file):
        try:
            with open(key_file, "rb") as f:
                old_fernet = Fernet(f.read().strip())
            plaintext = old_fernet.decrypt(stored.encode("utf-8")).decode("utf-8")
            data[token_field] = active.encrypt(plaintext.encode("utf-8")).decode("utf-8")
            with open(config_path, "w") as f:
                json.dump(data, f, indent=4)
            print(f"Upgraded {token_field!r} in {config_path} from the on-disk key to {env_key_var}.")
            return plaintext
        except Exception:
            pass

    # raw plaintext
    plaintext = stored
    data[token_field] = active.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    with open(config_path, "w") as f:
        json.dump(data, f, indent=4)
    print(f"Encrypted {token_field!r} in {config_path} at rest.")
    return plaintext
