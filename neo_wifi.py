import base58
import binascii
import os
from dotenv import load_dotenv
load_dotenv()

wif = os.getenv("NEO_WALLET_PRIVATE_KEY")
# 2. Decode
decoded = base58.b58decode(wif)
hex_string = binascii.hexlify(decoded).decode('utf-8')

# 3. Extract the raw key (Remove version byte and checksum)
# WIF structure: [Version 1 byte] + [Key 32 bytes] + [Compression 1 byte] + [Checksum 4 bytes]
# We want the 32 bytes in the middle.
raw_hex_key = hex_string[2:-10] 

print(f"NEO_WALLET_PRIVATE_KEY_HEX: {raw_hex_key}")