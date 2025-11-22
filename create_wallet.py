import os
import hashlib
import base58
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

def to_script_hash(script):
    sha = hashlib.sha256(script).digest()
    rip = hashlib.new('ripemd160', sha).digest()
    return rip

def create_wallet():
    # Generate key
    private_key = ec.generate_private_key(ec.SECP256R1())
    
    # Get private key bytes
    private_key_bytes = private_key.private_numbers().private_value.to_bytes(32, 'big')
    
    # Get compressed public key
    public_key = private_key.public_key()
    public_numbers = public_key.public_numbers()
    x = public_numbers.x
    y = public_numbers.y
    
    if y % 2 == 0:
        prefix = b'\x02'
    else:
        prefix = b'\x03'
        
    public_key_bytes = prefix + x.to_bytes(32, 'big')
    
    # Construct script
    # Standard Neo3 Single Sig: Push(PubKey) + SysCall(Neo.Crypto.CheckSig)
    # Push 33 bytes: 0x21
    # SysCall: 0x68
    # Neo.Crypto.CheckSig Hash: 0xac7fb4db (Murmur32)
    # Little Endian: db b4 7f ac
    
    # Note: Some sources say 0x0C ... but that might be specific to something else.
    # The standard verification script is what we need for the address.
    
    # Let's try the standard one.
    checksig_hash = bytes.fromhex("dbb47fac") # Little endian of 0xac7fb4db
    script = b'\x21' + public_key_bytes + b'\x68' + checksig_hash
    
    script_hash = to_script_hash(script)
    
    # Address
    # Version 0x35 (53) for N3
    version = b'\x35'
    address = base58.b58encode_check(version + script_hash).decode()
    
    # WIF
    # 0x80 + PrivateKey + 0x01 (compressed)
    wif_bytes = b'\x80' + private_key_bytes + b'\x01'
    wif = base58.b58encode_check(wif_bytes).decode()
    
    print(f"Address: {address}")
    print(f"WIF: {wif}")
    
    # Save to .env
    with open(".env", "w") as f:
        f.write(f"NEO_WALLET_ADDRESS={address}\n")
        f.write(f"NEO_WALLET_PRIVATE_KEY={wif}\n")
        # Also save the raw private key just in case
        f.write(f"NEO_WALLET_PRIVATE_KEY_HEX={private_key_bytes.hex()}\n")

if __name__ == "__main__":
    create_wallet()
